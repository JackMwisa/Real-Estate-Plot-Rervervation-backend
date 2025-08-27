from celery import shared_task
from django.utils import timezone
from django.db.models import Sum, Q
from datetime import timedelta
from decimal import Decimal

from .models import Wallet, LedgerEntry, Payout, WalletTransaction
from .services import PayoutService, LedgerService


@shared_task
def process_pending_payouts():
    """
    Process approved payouts that are queued
    Run this task every 15 minutes
    """
    # Get payouts ready for processing
    ready_payouts = Payout.objects.filter(
        status='queued',
        Q(requires_approval=False) | Q(approved_at__isnull=False)
    )
    
    processed_count = 0
    failed_count = 0
    
    for payout in ready_payouts:
        try:
            result = PayoutService.process_payout(payout)
            if result['status'] == 'success':
                processed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            # Log error and mark payout as failed
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
            failed_count += 1
    
    return {
        'processed_payouts': processed_count,
        'failed_payouts': failed_count,
        'processed_at': str(timezone.now())
    }


@shared_task
def refresh_wallet_balances():
    """
    Refresh cached wallet balances
    Run this task daily to ensure accuracy
    """
    wallets = Wallet.objects.filter(is_active=True)
    
    refreshed_count = 0
    mismatches_found = 0
    
    for wallet in wallets:
        old_balance = wallet.balance_cached
        wallet.refresh_balance()
        
        if old_balance != wallet.balance_cached:
            mismatches_found += 1
        
        refreshed_count += 1
    
    return {
        'refreshed_wallets': refreshed_count,
        'balance_mismatches': mismatches_found,
        'processed_at': str(timezone.now())
    }


@shared_task
def verify_ledger_integrity():
    """
    Verify ledger integrity and report issues
    Run this task daily
    """
    results = LedgerService.verify_ledger_invariants()
    
    # If there are violations, you might want to send alerts
    if results['invariant_violations'] or results['balance_mismatches']:
        # In production, send alerts to admin team
        pass
    
    return {
        'check_results': results,
        'processed_at': str(timezone.now())
    }


@shared_task
def cleanup_old_transactions():
    """
    Archive old completed transactions
    Run this task weekly
    """
    # Archive transactions older than 2 years
    cutoff_date = timezone.now() - timedelta(days=730)
    
    old_transactions = WalletTransaction.objects.filter(
        status__in=['completed', 'failed', 'cancelled'],
        updated_at__lt=cutoff_date
    )
    
    # In production, you might move these to an archive table
    archived_count = 0
    for transaction in old_transactions:
        transaction.metadata['archived_at'] = timezone.now().isoformat()
        transaction.save(update_fields=['metadata'])
        archived_count += 1
    
    return {
        'archived_transactions': archived_count,
        'cutoff_date': str(cutoff_date)
    }


@shared_task
def generate_wallet_reports():
    """
    Generate daily wallet and payout reports
    Run this task daily at midnight
    """
    from django.db.models import Count, Avg
    
    yesterday = timezone.now().date() - timedelta(days=1)
    
    # Daily transaction summary
    daily_entries = LedgerEntry.objects.filter(
        created_at__date=yesterday
    )
    
    transaction_summary = daily_entries.aggregate(
        total_entries=Count('id'),
        total_credits=Sum('amount', filter=Q(entry_type='credit')),
        total_debits=Sum('amount', filter=Q(entry_type='debit')),
        avg_transaction_size=Avg('amount')
    )
    
    # Daily payout summary
    daily_payouts = Payout.objects.filter(
        created_at__date=yesterday
    )
    
    payout_summary = daily_payouts.aggregate(
        total_payouts=Count('id'),
        successful_payouts=Count('id', filter=Q(status='paid')),
        failed_payouts=Count('id', filter=Q(status='failed')),
        total_payout_amount=Sum('amount'),
        avg_payout_amount=Avg('amount')
    )
    
    # Wallet growth
    new_wallets = Wallet.objects.filter(
        created_at__date=yesterday
    ).count()
    
    return {
        'report_date': str(yesterday),
        'transaction_summary': transaction_summary,
        'payout_summary': payout_summary,
        'new_wallets': new_wallets,
        'generated_at': str(timezone.now())
    }


@shared_task
def auto_process_small_payouts():
    """
    Auto-process small payouts that don't require approval
    Run this task every hour
    """
    # Auto-process payouts under $100 that have been queued for more than 1 hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    
    auto_process_payouts = Payout.objects.filter(
        status='queued',
        requires_approval=False,
        amount__lt=Decimal('100.00'),
        created_at__lt=one_hour_ago
    )
    
    processed_count = 0
    failed_count = 0
    
    for payout in auto_process_payouts:
        try:
            result = PayoutService.process_payout(payout)
            if result['status'] == 'success':
                processed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            payout.status = 'failed'
            payout.failure_reason = f"Auto-processing failed: {str(e)}"
            payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
            failed_count += 1
    
    return {
        'auto_processed': processed_count,
        'auto_failed': failed_count,
        'processed_at': str(timezone.now())
    }