from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
import uuid

from .models import Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider

User = get_user_model()


class WalletService:
    """Core wallet operations service"""
    
    @staticmethod
    def get_or_create_wallet(user=None, agency=None, wallet_type='user', currency='USD') -> Wallet:
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
    def create_ledger_entry(
        wallet: Wallet,
        entry_type: str,
        amount: Decimal,
        ref_type: str,
        ref_id: str,
        description: str,
        txid: Optional[uuid.UUID] = None,
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LedgerEntry:
        """Create a ledger entry and update wallet balance"""
        
        if txid is None:
            txid = uuid.uuid4()
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            entry_type=entry_type,
            amount=amount,
            currency=wallet.currency,
            ref_type=ref_type,
            ref_id=ref_id,
            txid=txid,
            description=description,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def transfer_funds(
        from_wallet: Wallet,
        to_wallet: Wallet,
        amount: Decimal,
        description: str,
        ref_type: str = 'transfer',
        ref_id: str = '',
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[LedgerEntry, LedgerEntry]:
        """Transfer funds between wallets with double-entry bookkeeping"""
        
        # Validate transfer
        can_debit, reason = from_wallet.can_debit(amount)
        if not can_debit:
            raise ValueError(f"Cannot debit from wallet: {reason}")
        
        if from_wallet.currency != to_wallet.currency:
            raise ValueError("Currency mismatch between wallets")
        
        # Generate transaction ID for grouping
        txid = uuid.uuid4()
        
        # Create transaction record
        wallet_transaction = WalletTransaction.objects.create(
            transaction_type='transfer',
            from_wallet=from_wallet,
            to_wallet=to_wallet,
            amount=amount,
            currency=from_wallet.currency,
            reference=f"TXN-{txid.hex[:8].upper()}",
            description=description,
            related_object_type=ref_type,
            related_object_id=ref_id,
            metadata=metadata or {}
        )
        
        # Create debit entry (from wallet)
        debit_entry = WalletService.create_ledger_entry(
            wallet=from_wallet,
            entry_type='debit',
            amount=amount,
            ref_type=ref_type,
            ref_id=ref_id,
            description=f"Transfer to {to_wallet.get_owner_display()}: {description}",
            txid=txid,
            created_by=created_by,
            metadata=metadata
        )
        
        # Create credit entry (to wallet)
        credit_entry = WalletService.create_ledger_entry(
            wallet=to_wallet,
            entry_type='credit',
            amount=amount,
            ref_type=ref_type,
            ref_id=ref_id,
            description=f"Transfer from {from_wallet.get_owner_display()}: {description}",
            txid=txid,
            created_by=created_by,
            metadata=metadata
        )
        
        # Mark transaction as completed
        wallet_transaction.status = 'completed'
        wallet_transaction.completed_at = timezone.now()
        wallet_transaction.save(update_fields=['status', 'completed_at', 'updated_at'])
        
        return debit_entry, credit_entry
    
    @staticmethod
    def credit_wallet(
        wallet: Wallet,
        amount: Decimal,
        ref_type: str,
        ref_id: str,
        description: str,
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LedgerEntry:
        """Credit funds to wallet"""
        return WalletService.create_ledger_entry(
            wallet=wallet,
            entry_type='credit',
            amount=amount,
            ref_type=ref_type,
            ref_id=ref_id,
            description=description,
            created_by=created_by,
            metadata=metadata
        )
    
    @staticmethod
    def debit_wallet(
        wallet: Wallet,
        amount: Decimal,
        ref_type: str,
        ref_id: str,
        description: str,
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LedgerEntry:
        """Debit funds from wallet"""
        
        # Validate debit
        can_debit, reason = wallet.can_debit(amount)
        if not can_debit:
            raise ValueError(f"Cannot debit wallet: {reason}")
        
        return WalletService.create_ledger_entry(
            wallet=wallet,
            entry_type='debit',
            amount=amount,
            ref_type=ref_type,
            ref_id=ref_id,
            description=description,
            created_by=created_by,
            metadata=metadata
        )


class PayoutService:
    """Service for managing payouts"""
    
    @staticmethod
    def create_payout(
        wallet: Wallet,
        beneficiary: Beneficiary,
        amount: Decimal,
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Payout:
        """Create a new payout request"""
        
        # Validate beneficiary
        if not beneficiary.can_receive_payouts:
            raise ValueError("Beneficiary cannot receive payouts (inactive or unverified)")
        
        if beneficiary.owner != wallet.get_owner():
            raise ValueError("Beneficiary must belong to wallet owner")
        
        # Validate wallet balance
        can_debit, reason = wallet.can_debit(amount)
        if not can_debit:
            raise ValueError(f"Cannot create payout: {reason}")
        
        # Get provider and calculate fees
        provider = PayoutService.get_provider_for_method(beneficiary.payout_method)
        if not provider:
            raise ValueError(f"No provider available for {beneficiary.payout_method}")
        
        fee_amount = provider.calculate_fee(amount, beneficiary.payout_method)
        
        # Check minimum payout amount
        if amount < provider.min_payout_amount:
            raise ValueError(f"Amount below minimum payout ({provider.min_payout_amount} {wallet.currency})")
        
        # Check maximum payout amount
        if provider.max_payout_amount and amount > provider.max_payout_amount:
            raise ValueError(f"Amount exceeds maximum payout ({provider.max_payout_amount} {wallet.currency})")
        
        # Create payout
        payout = Payout.objects.create(
            wallet=wallet,
            beneficiary=beneficiary,
            amount=amount,
            currency=wallet.currency,
            fee_amount=fee_amount,
            requires_approval=amount >= Decimal('1000.00'),  # Require approval for large amounts
            metadata=metadata or {}
        )
        
        # Create debit ledger entry (hold funds)
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
    def get_provider_for_method(method: str) -> Optional[PayoutProvider]:
        """Get active provider that supports the given method"""
        return PayoutProvider.objects.filter(
            is_active=True,
            supported_methods__contains=[method]
        ).first()
    
    @staticmethod
    def process_payout(payout: Payout) -> Dict[str, Any]:
        """Process a payout through the provider"""
        if payout.status != 'queued':
            raise ValueError("Payout must be in queued status")
        
        if payout.requires_approval and not payout.approved_at:
            raise ValueError("Payout requires approval before processing")
        
        provider = PayoutService.get_provider_for_method(payout.beneficiary.payout_method)
        if not provider:
            raise ValueError("No provider available")
        
        # Mark as processing
        payout.status = 'processing'
        payout.processed_at = timezone.now()
        payout.save(update_fields=['status', 'processed_at', 'updated_at'])
        
        try:
            # Here you would integrate with actual payout providers
            # For now, simulate successful processing
            result = PayoutService._simulate_provider_payout(payout, provider)
            
            if result['success']:
                payout.status = 'paid'
                payout.provider_ref = result.get('provider_ref', '')
                payout.completed_at = timezone.now()
                payout.save(update_fields=['status', 'provider_ref', 'completed_at', 'updated_at'])
                
                return {'status': 'success', 'provider_ref': payout.provider_ref}
            else:
                payout.status = 'failed'
                payout.failure_reason = result.get('error', 'Unknown error')
                payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
                
                # Refund the debited amount
                WalletService.credit_wallet(
                    wallet=payout.wallet,
                    amount=payout.amount,
                    ref_type='refund',
                    ref_id=str(payout.id),
                    description=f"Payout failed - refund for {payout.beneficiary.name}",
                    metadata={'original_payout_id': str(payout.id)}
                )
                
                return {'status': 'failed', 'error': payout.failure_reason}
        
        except Exception as e:
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
            
            # Refund the debited amount
            WalletService.credit_wallet(
                wallet=payout.wallet,
                amount=payout.amount,
                ref_type='refund',
                ref_id=str(payout.id),
                description=f"Payout failed - refund for {payout.beneficiary.name}",
                metadata={'original_payout_id': str(payout.id)}
            )
            
            return {'status': 'failed', 'error': str(e)}
    
    @staticmethod
    def _simulate_provider_payout(payout: Payout, provider: PayoutProvider) -> Dict[str, Any]:
        """Simulate payout processing (replace with real provider integration)"""
        import random
        
        # Simulate 95% success rate
        if random.random() < 0.95:
            return {
                'success': True,
                'provider_ref': f"{provider.code}-{uuid.uuid4().hex[:8].upper()}"
            }
        else:
            return {
                'success': False,
                'error': 'Provider temporarily unavailable'
            }


class LedgerService:
    """Service for ledger operations and invariant checking"""
    
    @staticmethod
    def verify_ledger_invariants(wallet: Optional[Wallet] = None) -> Dict[str, Any]:
        """Verify double-entry ledger invariants"""
        from django.db.models import Sum, Q
        
        if wallet:
            # Check specific wallet
            wallets_to_check = [wallet]
        else:
            # Check all wallets
            wallets_to_check = Wallet.objects.all()
        
        results = {
            'total_wallets_checked': len(wallets_to_check),
            'invariant_violations': [],
            'balance_mismatches': [],
            'orphaned_entries': 0
        }
        
        for wallet in wallets_to_check:
            # Calculate balance from ledger
            credits = wallet.ledger_entries.filter(
                entry_type='credit'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            debits = wallet.ledger_entries.filter(
                entry_type='debit'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            calculated_balance = credits - debits
            
            # Check balance mismatch
            if calculated_balance != wallet.balance_cached:
                results['balance_mismatches'].append({
                    'wallet_id': str(wallet.id),
                    'owner': wallet.get_owner_display(),
                    'cached_balance': wallet.balance_cached,
                    'calculated_balance': calculated_balance,
                    'difference': calculated_balance - wallet.balance_cached
                })
        
        # Check for orphaned ledger entries (entries without valid txid pairs)
        all_txids = LedgerEntry.objects.values_list('txid', flat=True).distinct()
        
        for txid in all_txids:
            entries = LedgerEntry.objects.filter(txid=txid)
            
            # For transfers, should have exactly 2 entries (1 credit, 1 debit)
            if entries.count() == 2:
                credit_sum = entries.filter(entry_type='credit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                
                debit_sum = entries.filter(entry_type='debit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                
                if credit_sum != debit_sum:
                    results['invariant_violations'].append({
                        'txid': str(txid),
                        'issue': 'Credit/debit mismatch',
                        'credit_sum': credit_sum,
                        'debit_sum': debit_sum
                    })
            elif entries.count() > 2:
                # Complex transaction - verify total credits = total debits
                credit_sum = entries.filter(entry_type='credit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                
                debit_sum = entries.filter(entry_type='debit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                
                if credit_sum != debit_sum:
                    results['invariant_violations'].append({
                        'txid': str(txid),
                        'issue': 'Complex transaction imbalance',
                        'credit_sum': credit_sum,
                        'debit_sum': debit_sum,
                        'entry_count': entries.count()
                    })
            elif entries.count() == 1:
                # Single entry - acceptable for deposits/withdrawals from external sources
                pass
        
        return results
    
    @staticmethod
    def get_wallet_statement(
        wallet: Wallet,
        start_date: Optional[timezone.datetime] = None,
        end_date: Optional[timezone.datetime] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Generate wallet statement"""
        
        queryset = wallet.ledger_entries.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        entries = queryset.order_by('-created_at')[:limit]
        
        # Calculate running balance
        statement_entries = []
        running_balance = wallet.balance_cached
        
        for entry in entries:
            if entry.entry_type == 'credit':
                running_balance -= entry.amount  # Reverse for historical balance
            else:
                running_balance += entry.amount
            
            statement_entries.append({
                'id': str(entry.id),
                'date': entry.created_at,
                'type': entry.entry_type,
                'amount': entry.amount,
                'description': entry.description,
                'ref_type': entry.ref_type,
                'balance_after': entry.balance_after,
                'txid': str(entry.txid)
            })
        
        # Reverse to show chronological order
        statement_entries.reverse()
        
        return {
            'wallet_id': str(wallet.id),
            'owner': wallet.get_owner_display(),
            'current_balance': wallet.balance_cached,
            'currency': wallet.currency,
            'statement_period': {
                'start': start_date,
                'end': end_date
            },
            'entries': statement_entries,
            'entry_count': len(statement_entries)
        }


class EscrowWalletService:
    """Service for escrow wallet operations"""
    
    @staticmethod
    def get_or_create_escrow_wallet(currency: str = 'USD') -> Wallet:
        """Get or create system escrow wallet"""
        wallet, created = Wallet.objects.get_or_create(
            wallet_type='escrow',
            currency=currency,
            defaults={
                'metadata': {'purpose': 'escrow_holding'}
            }
        )
        return wallet
    
    @staticmethod
    @transaction.atomic
    def hold_escrow_funds(
        buyer_wallet: Wallet,
        amount: Decimal,
        reservation_id: str,
        description: str = "Escrow hold"
    ) -> Tuple[LedgerEntry, LedgerEntry]:
        """Move funds from buyer wallet to escrow"""
        
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(buyer_wallet.currency)
        
        return WalletService.transfer_funds(
            from_wallet=buyer_wallet,
            to_wallet=escrow_wallet,
            amount=amount,
            description=description,
            ref_type='reservation',
            ref_id=reservation_id,
            metadata={'escrow_action': 'hold', 'reservation_id': reservation_id}
        )
    
    @staticmethod
    @transaction.atomic
    def release_escrow_funds(
        seller_wallet: Wallet,
        amount: Decimal,
        reservation_id: str,
        description: str = "Escrow release"
    ) -> Tuple[LedgerEntry, LedgerEntry]:
        """Release funds from escrow to seller"""
        
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(seller_wallet.currency)
        
        return WalletService.transfer_funds(
            from_wallet=escrow_wallet,
            to_wallet=seller_wallet,
            amount=amount,
            description=description,
            ref_type='reservation',
            ref_id=reservation_id,
            metadata={'escrow_action': 'release', 'reservation_id': reservation_id}
        )
    
    @staticmethod
    @transaction.atomic
    def refund_escrow_funds(
        buyer_wallet: Wallet,
        amount: Decimal,
        reservation_id: str,
        description: str = "Escrow refund"
    ) -> Tuple[LedgerEntry, LedgerEntry]:
        """Refund funds from escrow to buyer"""
        
        escrow_wallet = EscrowWalletService.get_or_create_escrow_wallet(buyer_wallet.currency)
        
        return WalletService.transfer_funds(
            from_wallet=escrow_wallet,
            to_wallet=buyer_wallet,
            amount=amount,
            description=description,
            ref_type='reservation',
            ref_id=reservation_id,
            metadata={'escrow_action': 'refund', 'reservation_id': reservation_id}
        )