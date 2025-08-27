from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
import uuid
import requests

from .models import (
    Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider,
    CurrencyExchangeRate, CommissionRule, SavingsGoal, SecurityAlert,
    WalletAnalytics, InvestmentPool, Investment
)

User = get_user_model()


class WalletService:
    """Core wallet operations service"""
    
    @staticmethod
    def get_or_create_wallet(user=None, agency=None, wallet_type='user', currency='USD'):
        """Get or create wallet for user or agency"""
        if user:
            wallet, created = Wallet.objects.get_or_create(
                owner_user=user,
                defaults={
                    'wallet_type': wallet_type,
                    'currency': currency
                }
            )
        elif agency:
            wallet, created = Wallet.objects.get_or_create(
                owner_agency=agency,
                defaults={
                    'wallet_type': 'agency',
                    'currency': currency
                }
            )
        else:
            raise ValueError("Either user or agency must be provided")
        
        return wallet

    @staticmethod
    @transaction.atomic
    def credit_wallet(wallet, amount, ref_type, ref_id, description, created_by=None, metadata=None):
        """Credit wallet with double-entry ledger"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        # Generate transaction ID
        txid = uuid.uuid4()
        
        # Create credit entry
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            entry_type='credit',
            amount=amount,
            currency=wallet.currency,
            ref_type=ref_type,
            ref_id=ref_id,
            txid=txid,
            description=description,
            balance_after=wallet.balance_cached + amount,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        # Update wallet balance
        wallet.balance_cached += amount
        wallet.last_activity_at = timezone.now()
        wallet.save(update_fields=['balance_cached', 'last_activity_at'])
        
        return entry

    @staticmethod
    @transaction.atomic
    def debit_wallet(wallet, amount, ref_type, ref_id, description, created_by=None, metadata=None):
        """Debit wallet with validation"""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        can_debit, reason = wallet.can_debit(amount)
        if not can_debit:
            raise ValueError(f"Cannot debit wallet: {reason}")
        
        # Generate transaction ID
        txid = uuid.uuid4()
        
        # Create debit entry
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            entry_type='debit',
            amount=amount,
            currency=wallet.currency,
            ref_type=ref_type,
            ref_id=ref_id,
            txid=txid,
            description=description,
            balance_after=wallet.balance_cached - amount,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        # Update wallet balance
        wallet.balance_cached -= amount
        wallet.last_activity_at = timezone.now()
        wallet.save(update_fields=['balance_cached', 'last_activity_at'])
        
        return entry

    @staticmethod
    @transaction.atomic
    def transfer_funds(from_wallet, to_wallet, amount, description, created_by=None, metadata=None):
        """Transfer funds between wallets"""
        if from_wallet.currency != to_wallet.currency:
            raise ValueError("Currency mismatch between wallets")
        
        # Generate shared transaction ID
        txid = uuid.uuid4()
        
        # Create debit entry for sender
        debit_entry = LedgerEntry.objects.create(
            wallet=from_wallet,
            entry_type='debit',
            amount=amount,
            currency=from_wallet.currency,
            ref_type='transfer',
            ref_id=str(to_wallet.id),
            txid=txid,
            description=f"Transfer to {to_wallet.get_owner_display()}: {description}",
            balance_after=from_wallet.balance_cached - amount,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        # Create credit entry for receiver
        credit_entry = LedgerEntry.objects.create(
            wallet=to_wallet,
            entry_type='credit',
            amount=amount,
            currency=to_wallet.currency,
            ref_type='transfer',
            ref_id=str(from_wallet.id),
            txid=txid,
            description=f"Transfer from {from_wallet.get_owner_display()}: {description}",
            balance_after=to_wallet.balance_cached + amount,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        # Update wallet balances
        from_wallet.balance_cached -= amount
        from_wallet.last_activity_at = timezone.now()
        from_wallet.save(update_fields=['balance_cached', 'last_activity_at'])
        
        to_wallet.balance_cached += amount
        to_wallet.last_activity_at = timezone.now()
        to_wallet.save(update_fields=['balance_cached', 'last_activity_at'])
        
        return debit_entry, credit_entry


class CurrencyService:
    """Multi-currency exchange service"""
    
    @staticmethod
    def get_exchange_rate(from_currency, to_currency):
        """Get latest exchange rate"""
        if from_currency == to_currency:
            return Decimal('1.00')
        
        # Try to get latest rate
        rate = CurrencyExchangeRate.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()
        
        if rate:
            return rate.rate
        
        # Try reverse rate
        reverse_rate = CurrencyExchangeRate.objects.filter(
            from_currency=to_currency,
            to_currency=from_currency,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()
        
        if reverse_rate:
            return Decimal('1.00') / reverse_rate.rate
        
        raise ValueError(f"No exchange rate found for {from_currency} to {to_currency}")

    @staticmethod
    def convert_amount(amount, from_currency, to_currency):
        """Convert amount between currencies"""
        if from_currency == to_currency:
            return amount
        
        rate = CurrencyService.get_exchange_rate(from_currency, to_currency)
        return amount * rate

    @staticmethod
    def update_exchange_rates():
        """Update exchange rates from external API"""
        # This would integrate with a real exchange rate API
        # For now, just update with mock rates
        rates = [
            ('USD', 'UGX', Decimal('3700.00')),
            ('EUR', 'USD', Decimal('1.08')),
            ('GBP', 'USD', Decimal('1.25')),
        ]
        
        for from_curr, to_curr, rate in rates:
            CurrencyExchangeRate.objects.update_or_create(
                from_currency=from_curr,
                to_currency=to_curr,
                provider='manual',
                defaults={
                    'rate': rate,
                    'expires_at': timezone.now() + timezone.timedelta(hours=24)
                }
            )


class CommissionService:
    """Commission calculation and distribution service"""
    
    @staticmethod
    def calculate_commissions(amount, transaction_type, context=None):
        """Calculate all applicable commissions for a transaction"""
        rules = CommissionRule.objects.filter(
            is_active=True,
            applies_to__in=['all', transaction_type]
        ).order_by('priority')
        
        commissions = []
        
        for rule in rules:
            # Check amount limits
            if rule.min_transaction_amount and amount < rule.min_transaction_amount:
                continue
            if rule.max_transaction_amount and amount > rule.max_transaction_amount:
                continue
            
            # Check target conditions
            if rule.target_conditions and context:
                if not CommissionService._check_conditions(rule.target_conditions, context):
                    continue
            
            commission_amount = rule.calculate_commission(amount)
            if commission_amount > 0:
                commissions.append({
                    'rule': rule,
                    'amount': commission_amount,
                    'description': f"{rule.name}: {commission_amount}"
                })
        
        return commissions

    @staticmethod
    def _check_conditions(conditions, context):
        """Check if context meets rule conditions"""
        # Simple condition checking - can be enhanced
        for key, value in conditions.items():
            if key not in context or context[key] != value:
                return False
        return True

    @staticmethod
    @transaction.atomic
    def distribute_commissions(source_wallet, amount, transaction_type, ref_id, context=None):
        """Calculate and distribute commissions"""
        commissions = CommissionService.calculate_commissions(amount, transaction_type, context)
        
        total_commission = Decimal('0.00')
        commission_entries = []
        
        for commission in commissions:
            rule = commission['rule']
            commission_amount = commission['amount']
            
            # Get platform wallet for commission collection
            platform_wallet = Wallet.objects.get_or_create(
                wallet_type='platform',
                currency=source_wallet.currency,
                defaults={'owner_user': None, 'owner_agency': None}
            )[0]
            
            # Transfer commission to platform
            debit_entry, credit_entry = WalletService.transfer_funds(
                from_wallet=source_wallet,
                to_wallet=platform_wallet,
                amount=commission_amount,
                description=f"Commission: {rule.name}",
                metadata={'commission_rule_id': rule.id, 'ref_id': ref_id}
            )
            
            commission_entries.append({
                'rule': rule,
                'amount': commission_amount,
                'debit_entry': debit_entry,
                'credit_entry': credit_entry
            })
            
            total_commission += commission_amount
        
        return commission_entries, total_commission


class SecurityService:
    """Wallet security monitoring service"""
    
    @staticmethod
    def check_transaction_security(wallet, amount, transaction_type):
        """Check transaction for security issues"""
        alerts = []
        
        # Large transaction check
        large_threshold = getattr(settings, 'WALLET_LARGE_TRANSACTION_THRESHOLD', Decimal('1000.00'))
        if amount >= large_threshold:
            alerts.append({
                'type': 'large_transaction',
                'severity': 'medium',
                'title': f'Large {transaction_type} transaction',
                'description': f'Transaction of {amount} {wallet.currency} detected',
                'data': {'amount': str(amount), 'type': transaction_type}
            })
        
        # Rapid transaction check
        recent_transactions = wallet.ledger_entries.filter(
            created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).count()
        
        if recent_transactions >= 5:
            alerts.append({
                'type': 'rapid_transactions',
                'severity': 'high',
                'title': 'Rapid transaction pattern detected',
                'description': f'{recent_transactions} transactions in last 5 minutes',
                'data': {'count': recent_transactions, 'timeframe': '5_minutes'}
            })
        
        # Create security alerts
        for alert_data in alerts:
            SecurityAlert.objects.create(
                wallet=wallet,
                alert_type=alert_data['type'],
                severity=alert_data['severity'],
                title=alert_data['title'],
                description=alert_data['description'],
                alert_data=alert_data['data']
            )
        
        return alerts


class PayoutService:
    """Payout processing service"""
    
    @staticmethod
    def create_payout(wallet, beneficiary, amount, created_by=None):
        """Create payout with validation and fee calculation"""
        if not beneficiary.can_receive_payouts:
            raise ValueError("Beneficiary cannot receive payouts")
        
        # Calculate fees
        fee_amount = PayoutService._calculate_fee(amount, beneficiary.payout_method)
        net_amount = amount - fee_amount
        
        # Check if requires approval
        approval_threshold = getattr(settings, 'PAYOUT_APPROVAL_THRESHOLD', Decimal('500.00'))
        requires_approval = amount >= approval_threshold
        
        # Create payout
        payout = Payout.objects.create(
            wallet=wallet,
            beneficiary=beneficiary,
            amount=amount,
            currency=wallet.currency,
            fee_amount=fee_amount,
            net_amount=net_amount,
            requires_approval=requires_approval
        )
        
        # Debit wallet immediately (hold funds)
        WalletService.debit_wallet(
            wallet=wallet,
            amount=amount,
            ref_type='payout',
            ref_id=str(payout.id),
            description=f"Payout to {beneficiary.name}",
            created_by=created_by,
            metadata={'payout_id': str(payout.id)}
        )
        
        return payout

    @staticmethod
    def _calculate_fee(amount, payout_method):
        """Calculate payout fee based on method and amount"""
        # Simple fee structure - can be enhanced
        fee_rates = {
            'bank_transfer': Decimal('2.50'),  # Fixed fee
            'mobile_money': Decimal('1.00'),   # Fixed fee
            'paypal': amount * Decimal('0.029'),  # 2.9%
            'crypto': Decimal('5.00'),         # Fixed fee
        }
        
        return fee_rates.get(payout_method, Decimal('0.00'))

    @staticmethod
    def process_payout(payout):
        """Process payout through provider"""
        if payout.status != 'queued':
            raise ValueError("Payout is not in queued status")
        
        if payout.requires_approval and not payout.approved_at:
            raise ValueError("Payout requires approval")
        
        # Update status
        payout.status = 'processing'
        payout.processed_at = timezone.now()
        payout.save(update_fields=['status', 'processed_at'])
        
        try:
            # Process through provider (mock implementation)
            provider_ref = f"PAY-{uuid.uuid4().hex[:8].upper()}"
            
            # Simulate processing
            payout.status = 'paid'
            payout.provider_ref = provider_ref
            payout.completed_at = timezone.now()
            payout.save(update_fields=['status', 'provider_ref', 'completed_at'])
            
            return {
                'status': 'success',
                'provider_ref': provider_ref,
                'message': 'Payout processed successfully'
            }
            
        except Exception as e:
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.save(update_fields=['status', 'failure_reason'])
            
            # Refund amount back to wallet
            WalletService.credit_wallet(
                wallet=payout.wallet,
                amount=payout.amount,
                ref_type='refund',
                ref_id=str(payout.id),
                description=f"Payout failed - refund for {payout.beneficiary.name}",
                metadata={'failed_payout_id': str(payout.id)}
            )
            
            return {
                'status': 'failed',
                'error': str(e),
                'message': 'Payout failed and amount refunded'
            }


class SavingsService:
    """Savings goals and auto-save service"""
    
    @staticmethod
    def create_savings_goal(wallet, name, target_amount, target_date=None, auto_save_amount=None, auto_save_frequency=None):
        """Create savings goal"""
        goal = SavingsGoal.objects.create(
            wallet=wallet,
            name=name,
            target_amount=target_amount,
            currency=wallet.currency,
            target_date=target_date,
            auto_save_enabled=bool(auto_save_amount),
            auto_save_amount=auto_save_amount,
            auto_save_frequency=auto_save_frequency
        )
        
        return goal

    @staticmethod
    @transaction.atomic
    def contribute_to_goal(goal, amount, created_by=None):
        """Add contribution to savings goal"""
        # Create ledger entry
        WalletService.debit_wallet(
            wallet=goal.wallet,
            amount=amount,
            ref_type='savings',
            ref_id=str(goal.id),
            description=f"Savings contribution: {goal.name}",
            created_by=created_by,
            metadata={'savings_goal_id': str(goal.id)}
        )
        
        # Update goal
        goal.current_amount += amount
        if goal.current_amount >= goal.target_amount:
            goal.status = 'completed'
            goal.completed_at = timezone.now()
        
        goal.save(update_fields=['current_amount', 'status', 'completed_at'])
        
        return goal

    @staticmethod
    def process_auto_saves():
        """Process automatic savings contributions"""
        goals = SavingsGoal.objects.filter(
            auto_save_enabled=True,
            status='active'
        )
        
        processed = 0
        
        for goal in goals:
            if SavingsService._should_auto_save(goal):
                try:
                    SavingsService.contribute_to_goal(goal, goal.auto_save_amount)
                    goal.last_auto_save = timezone.now()
                    goal.save(update_fields=['last_auto_save'])
                    processed += 1
                except ValueError:
                    # Insufficient funds - skip this goal
                    pass
        
        return processed

    @staticmethod
    def _should_auto_save(goal):
        """Check if goal should auto-save now"""
        if not goal.auto_save_enabled or not goal.auto_save_amount:
            return False
        
        if not goal.last_auto_save:
            return True
        
        now = timezone.now()
        
        if goal.auto_save_frequency == 'daily':
            return (now - goal.last_auto_save).days >= 1
        elif goal.auto_save_frequency == 'weekly':
            return (now - goal.last_auto_save).days >= 7
        elif goal.auto_save_frequency == 'monthly':
            return (now - goal.last_auto_save).days >= 30
        
        return False


class InvestmentService:
    """Investment pool management service"""
    
    @staticmethod
    @transaction.atomic
    def create_investment(pool, investor, amount):
        """Create investment in pool"""
        if amount < pool.min_investment:
            raise ValueError(f"Minimum investment is {pool.min_investment} {pool.currency}")
        
        if pool.max_investment and amount > pool.max_investment:
            raise ValueError(f"Maximum investment is {pool.max_investment} {pool.currency}")
        
        if pool.status != 'open':
            raise ValueError("Investment pool is not open for investments")
        
        # Get investor wallet
        wallet = WalletService.get_or_create_wallet(user=investor, currency=pool.currency)
        
        # Check if investor already has investment in this pool
        existing = Investment.objects.filter(pool=pool, investor=investor).first()
        if existing:
            # Add to existing investment
            existing.amount += amount
            existing.save(update_fields=['amount', 'updated_at'])
            investment = existing
        else:
            # Create new investment
            investment = Investment.objects.create(
                pool=pool,
                investor=investor,
                amount=amount,
                currency=pool.currency
            )
        
        # Debit investor wallet
        WalletService.debit_wallet(
            wallet=wallet,
            amount=amount,
            ref_type='investment',
            ref_id=str(pool.id),
            description=f"Investment in {pool.name}",
            metadata={'pool_id': str(pool.id), 'investment_id': str(investment.id)}
        )
        
        # Update pool
        pool.current_amount += amount
        if pool.current_amount >= pool.target_amount:
            pool.status = 'funding'
        pool.save(update_fields=['current_amount', 'status'])
        
        return investment

    @staticmethod
    @transaction.atomic
    def distribute_returns(pool, total_return_amount):
        """Distribute returns to investors proportionally"""
        if pool.current_amount <= 0:
            return []
        
        investments = pool.investments.filter(status='active')
        distributions = []
        
        for investment in investments:
            # Calculate proportional return
            proportion = investment.amount / pool.current_amount
            return_amount = total_return_amount * proportion
            
            if return_amount > 0:
                # Credit investor wallet
                wallet = WalletService.get_or_create_wallet(
                    user=investment.investor, 
                    currency=pool.currency
                )
                
                entry = WalletService.credit_wallet(
                    wallet=wallet,
                    amount=return_amount,
                    ref_type='investment_return',
                    ref_id=str(pool.id),
                    description=f"Investment return from {pool.name}",
                    metadata={'pool_id': str(pool.id), 'investment_id': str(investment.id)}
                )
                
                # Update investment
                investment.returns_earned += return_amount
                investment.last_return_payment = timezone.now()
                investment.save(update_fields=['returns_earned', 'last_return_payment'])
                
                distributions.append({
                    'investment': investment,
                    'amount': return_amount,
                    'entry': entry
                })
        
        return distributions


class LedgerService:
    """Ledger integrity and reporting service"""
    
    @staticmethod
    def verify_ledger_invariants(wallet=None):
        """Verify double-entry ledger invariants"""
        if wallet:
            wallets = [wallet]
        else:
            wallets = Wallet.objects.all()
        
        violations = []
        balance_mismatches = []
        
        for wallet in wallets:
            # Check if credits equal debits for transfers
            transfer_entries = wallet.ledger_entries.filter(ref_type='transfer')
            transfer_txids = transfer_entries.values_list('txid', flat=True).distinct()
            
            for txid in transfer_txids:
                entries = LedgerEntry.objects.filter(txid=txid)
                total_credits = entries.filter(entry_type='credit').aggregate(
                    total=models.Sum('amount')
                )['total'] or Decimal('0.00')
                
                total_debits = entries.filter(entry_type='debit').aggregate(
                    total=models.Sum('amount')
                )['total'] or Decimal('0.00')
                
                if total_credits != total_debits:
                    violations.append({
                        'wallet_id': str(wallet.id),
                        'txid': str(txid),
                        'credits': str(total_credits),
                        'debits': str(total_debits),
                        'difference': str(total_credits - total_debits)
                    })
            
            # Check cached vs calculated balance
            if wallet.balance_cached != wallet.calculated_balance:
                balance_mismatches.append({
                    'wallet_id': str(wallet.id),
                    'cached_balance': str(wallet.balance_cached),
                    'calculated_balance': str(wallet.calculated_balance),
                    'difference': str(wallet.balance_cached - wallet.calculated_balance)
                })
        
        # Check for orphaned entries
        orphaned_count = LedgerEntry.objects.filter(
            ref_type='transfer'
        ).values('txid').annotate(
            entry_count=models.Count('id')
        ).filter(entry_count=1).count()
        
        return {
            'total_wallets_checked': len(wallets),
            'invariant_violations': violations,
            'balance_mismatches': balance_mismatches,
            'orphaned_entries': orphaned_count
        }

    @staticmethod
    def get_wallet_statement(wallet, start_date=None, end_date=None, limit=50):
        """Get wallet statement with running balances"""
        queryset = wallet.ledger_entries.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        entries = list(queryset[:limit])
        
        # Calculate summary
        total_credits = sum(e.amount for e in entries if e.entry_type == 'credit')
        total_debits = sum(e.amount for e in entries if e.entry_type == 'debit')
        
        return {
            'entries': entries,
            'summary': {
                'total_credits': total_credits,
                'total_debits': total_debits,
                'net_change': total_credits - total_debits,
                'entry_count': len(entries)
            },
            'wallet': {
                'current_balance': wallet.balance_cached,
                'currency': wallet.currency
            }
        }


class AnalyticsService:
    """Wallet analytics and insights service"""
    
    @staticmethod
    def generate_daily_analytics(date=None):
        """Generate daily analytics for all wallets"""
        if not date:
            date = timezone.now().date()
        
        wallets = Wallet.objects.filter(is_active=True)
        
        for wallet in wallets:
            # Get day's transactions
            day_entries = wallet.ledger_entries.filter(created_at__date=date)
            
            if not day_entries.exists():
                continue
            
            # Calculate metrics
            credits = day_entries.filter(entry_type='credit').aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0.00')
            
            debits = day_entries.filter(entry_type='debit').aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0.00')
            
            largest_transaction = day_entries.aggregate(
                largest=models.Max('amount')
            )['largest'] or Decimal('0.00')
            
            # Get opening balance (balance before first transaction of day)
            first_entry = day_entries.order_by('created_at').first()
            if first_entry.entry_type == 'credit':
                opening_balance = first_entry.balance_after - first_entry.amount
            else:
                opening_balance = first_entry.balance_after + first_entry.amount
            
            # Get closing balance (balance after last transaction of day)
            last_entry = day_entries.order_by('-created_at').first()
            closing_balance = last_entry.balance_after
            
            # Create or update analytics
            WalletAnalytics.objects.update_or_create(
                wallet=wallet,
                date=date,
                defaults={
                    'opening_balance': opening_balance,
                    'closing_balance': closing_balance,
                    'total_credits': credits,
                    'total_debits': debits,
                    'transaction_count': day_entries.count(),
                    'largest_transaction': largest_transaction
                }
            )

    @staticmethod
    def get_spending_insights(wallet, days=30):
        """Get spending insights for wallet"""
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        entries = wallet.ledger_entries.filter(
            created_at__gte=start_date,
            entry_type='debit'
        )
        
        # Group by ref_type
        spending_by_type = entries.values('ref_type').annotate(
            total=models.Sum('amount'),
            count=models.Count('id')
        ).order_by('-total')
        
        # Calculate trends
        total_spent = entries.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        avg_transaction = total_spent / entries.count() if entries.count() > 0 else Decimal('0.00')
        
        return {
            'period_days': days,
            'total_spent': total_spent,
            'transaction_count': entries.count(),
            'average_transaction': avg_transaction,
            'spending_by_type': list(spending_by_type),
            'currency': wallet.currency
        }


class EscrowWalletService:
    """Escrow wallet management for secure transactions"""
    
    @staticmethod
    def get_or_create_escrow_wallet(currency='USD'):
        """Get or create escrow wallet for currency"""
        wallet, created = Wallet.objects.get_or_create(
            wallet_type='escrow',
            currency=currency,
            defaults={
                'owner_user': None,
                'owner_agency': None
            }
        )
        return wallet

    @staticmethod
    @transaction.atomic
    def hold_escrow_funds(buyer_wallet, amount, reservation_id):
        """Move funds from buyer to escrow"""
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(buyer_wallet.currency)
        
        debit_entry, credit_entry = WalletService.transfer_funds(
            from_wallet=buyer_wallet,
            to_wallet=escrow_wallet,
            amount=amount,
            description=f"Escrow hold for reservation {reservation_id}",
            metadata={'reservation_id': reservation_id, 'escrow_action': 'hold'}
        )
        
        return debit_entry, credit_entry

    @staticmethod
    @transaction.atomic
    def release_escrow_funds(seller_wallet, amount, reservation_id):
        """Release funds from escrow to seller"""
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(seller_wallet.currency)
        
        debit_entry, credit_entry = WalletService.transfer_funds(
            from_wallet=escrow_wallet,
            to_wallet=seller_wallet,
            amount=amount,
            description=f"Escrow release for reservation {reservation_id}",
            metadata={'reservation_id': reservation_id, 'escrow_action': 'release'}
        )
        
        return debit_entry, credit_entry

    @staticmethod
    @transaction.atomic
    def refund_escrow_funds(buyer_wallet, amount, reservation_id):
        """Refund funds from escrow to buyer"""
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(buyer_wallet.currency)
        
        debit_entry, credit_entry = WalletService.transfer_funds(
            from_wallet=escrow_wallet,
            to_wallet=buyer_wallet,
            amount=amount,
            description=f"Escrow refund for reservation {reservation_id}",
            metadata={'reservation_id': reservation_id, 'escrow_action': 'refund'}
        )
        
        return debit_entry, credit_entry