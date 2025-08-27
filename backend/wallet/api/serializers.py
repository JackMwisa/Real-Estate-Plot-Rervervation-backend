from rest_framework import serializers
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models import Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider

User = get_user_model()


class WalletSerializer(serializers.ModelSerializer):
    owner_display = serializers.CharField(source='get_owner_display', read_only=True)
    calculated_balance = serializers.ReadOnlyField()
    can_debit_100 = serializers.SerializerMethodField()
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'owner_user', 'owner_agency', 'owner_display', 'wallet_type',
            'balance_cached', 'calculated_balance', 'currency', 'is_active',
            'daily_limit', 'monthly_limit', 'last_activity_at', 'created_at',
            'updated_at', 'can_debit_100', 'metadata'
        ]
        read_only_fields = [
            'id', 'balance_cached', 'last_activity_at', 'created_at', 'updated_at'
        ]

    def get_can_debit_100(self, obj):
        can_debit, reason = obj.can_debit(Decimal('100.00'))
        return {'can_debit': can_debit, 'reason': reason}


class LedgerEntrySerializer(serializers.ModelSerializer):
    wallet_owner = serializers.CharField(source='wallet.get_owner_display', read_only=True)
    balance_after = serializers.ReadOnlyField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = LedgerEntry
        fields = [
            'id', 'wallet', 'wallet_owner', 'entry_type', 'amount', 'currency',
            'ref_type', 'ref_id', 'txid', 'description', 'balance_after',
            'created_at', 'created_by', 'created_by_username', 'metadata'
        ]
        read_only_fields = ['id', 'balance_after', 'created_at']


class BeneficiarySerializer(serializers.ModelSerializer):
    can_receive_payouts = serializers.ReadOnlyField()
    
    class Meta:
        model = Beneficiary
        fields = [
            'id', 'owner', 'name', 'email', 'phone_number', 'kyc_status',
            'kyc_documents', 'kyc_verified_at', 'payout_method', 'payout_details',
            'is_active', 'is_default', 'can_receive_payouts', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'kyc_verified_at', 'created_at', 'updated_at'
        ]

    def validate_payout_details(self, value):
        """Validate payout details based on method"""
        method = self.initial_data.get('payout_method')
        
        if method == 'bank_transfer':
            required_fields = ['account_number', 'bank_name', 'account_name']
            for field in required_fields:
                if not value.get(field):
                    raise serializers.ValidationError(f"{field} is required for bank transfers")
        
        elif method == 'mobile_money':
            if not value.get('phone_number'):
                raise serializers.ValidationError("Phone number is required for mobile money")
        
        elif method == 'paypal':
            if not value.get('email'):
                raise serializers.ValidationError("Email is required for PayPal")
        
        return value


class PayoutSerializer(serializers.ModelSerializer):
    wallet_owner = serializers.CharField(source='wallet.get_owner_display', read_only=True)
    beneficiary_name = serializers.CharField(source='beneficiary.name', read_only=True)
    can_be_cancelled = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)
    
    class Meta:
        model = Payout
        fields = [
            'id', 'wallet', 'wallet_owner', 'beneficiary', 'beneficiary_name',
            'amount', 'currency', 'fee_amount', 'net_amount', 'status',
            'provider_ref', 'failure_reason', 'requires_approval', 'approved_by',
            'approved_by_username', 'approved_at', 'can_be_cancelled', 'is_completed',
            'created_at', 'updated_at', 'processed_at', 'completed_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'wallet', 'net_amount', 'fee_amount', 'status', 'provider_ref',
            'failure_reason', 'approved_by', 'approved_at', 'created_at',
            'updated_at', 'processed_at', 'completed_at'
        ]


class PayoutCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payouts"""
    
    class Meta:
        model = Payout
        fields = ['beneficiary', 'amount']

    def validate_beneficiary(self, value):
        """Ensure beneficiary belongs to current user"""
        user = self.context['request'].user
        if value.owner != user:
            raise serializers.ValidationError("You can only create payouts to your own beneficiaries")
        
        if not value.can_receive_payouts:
            raise serializers.ValidationError("Beneficiary cannot receive payouts (inactive or unverified)")
        
        return value

    def validate_amount(self, value):
        """Validate payout amount"""
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Amount must be positive")
        
        # Check against user's wallet balance
        user = self.context['request'].user
        try:
            wallet = user.wallet
            can_debit, reason = wallet.can_debit(value)
            if not can_debit:
                raise serializers.ValidationError(f"Cannot create payout: {reason}")
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("User wallet not found")
        
        return value


class WalletTransactionSerializer(serializers.ModelSerializer):
    from_wallet_owner = serializers.CharField(source='from_wallet.get_owner_display', read_only=True)
    to_wallet_owner = serializers.CharField(source='to_wallet.get_owner_display', read_only=True)
    is_transfer = serializers.ReadOnlyField()
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'transaction_type', 'from_wallet', 'from_wallet_owner',
            'to_wallet', 'to_wallet_owner', 'amount', 'currency', 'status',
            'reference', 'description', 'external_ref', 'related_object_type',
            'related_object_id', 'is_transfer', 'created_at', 'updated_at',
            'completed_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'completed_at'
        ]


class PayoutProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutProvider
        fields = [
            'id', 'name', 'code', 'supported_methods', 'supported_currencies',
            'fee_structure', 'min_payout_amount', 'max_payout_amount', 'is_active'
        ]
        read_only_fields = ['id']


class WalletBalanceSerializer(serializers.Serializer):
    """Serializer for wallet balance summary"""
    
    balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    pending_payouts = serializers.DecimalField(max_digits=15, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    last_activity = serializers.DateTimeField()


class TransferFundsSerializer(serializers.Serializer):
    """Serializer for wallet-to-wallet transfers"""
    
    to_wallet_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=500)
    
    def validate_to_wallet_id(self, value):
        try:
            wallet = Wallet.objects.get(id=value, is_active=True)
            return wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Target wallet not found or inactive")
    
    def validate(self, data):
        # Get user's wallet
        user = self.context['request'].user
        try:
            from_wallet = user.wallet
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("User wallet not found")
        
        to_wallet = data['to_wallet_id']
        amount = data['amount']
        
        # Validate transfer
        if from_wallet == to_wallet:
            raise serializers.ValidationError("Cannot transfer to the same wallet")
        
        if from_wallet.currency != to_wallet.currency:
            raise serializers.ValidationError("Currency mismatch between wallets")
        
        can_debit, reason = from_wallet.can_debit(amount)
        if not can_debit:
            raise serializers.ValidationError(f"Cannot transfer: {reason}")
        
        data['from_wallet'] = from_wallet
        return data


class LedgerInvariantSerializer(serializers.Serializer):
    """Serializer for ledger invariant check results"""
    
    total_wallets_checked = serializers.IntegerField()
    invariant_violations = serializers.ListField()
    balance_mismatches = serializers.ListField()
    orphaned_entries = serializers.IntegerField()