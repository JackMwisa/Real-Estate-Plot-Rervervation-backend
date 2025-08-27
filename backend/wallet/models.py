from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()


class Wallet(models.Model):
    """User/Agency wallet for holding funds"""
    
    WALLET_TYPE_CHOICES = [
        ('user', 'User Wallet'),
        ('agency', 'Agency Wallet'),
        ('escrow', 'Escrow Wallet'),
        ('system', 'System Wallet'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Owner (can be User or Agency profile)
    owner_user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='wallet'
    )
    owner_agency = models.OneToOneField(
        'users.Profile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='agency_wallet'
    )
    
    wallet_type = models.CharField(max_length=10, choices=WALLET_TYPE_CHOICES, default='user')
    
    # Cached balance (updated by ledger entries)
    balance_cached = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Status and limits
    is_active = models.BooleanField(default=True)
    daily_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Daily transaction limit"
    )
    monthly_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Monthly transaction limit"
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['wallet_type', 'is_active']),
            models.Index(fields=['currency']),
        ]

    def __str__(self):
        owner = self.get_owner_display()
        return f"{owner} Wallet ({self.currency} {self.balance_cached})"

    def get_owner_display(self):
        if self.owner_user:
            return self.owner_user.username
        elif self.owner_agency:
            return self.owner_agency.agency_name or f"Agency {self.owner_agency.id}"
        return f"System Wallet {self.id}"

    def get_owner(self):
        """Get the actual owner object"""
        return self.owner_user or self.owner_agency

    @property
    def calculated_balance(self):
        """Calculate balance from ledger entries"""
        from django.db.models import Sum, Q
        
        credits = self.ledger_entries.filter(
            entry_type='credit'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        debits = self.ledger_entries.filter(
            entry_type='debit'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        return credits - debits

    def refresh_balance(self):
        """Recalculate and update cached balance"""
        self.balance_cached = self.calculated_balance
        self.last_activity_at = timezone.now()
        self.save(update_fields=['balance_cached', 'last_activity_at', 'updated_at'])

    def can_debit(self, amount: Decimal) -> tuple[bool, str]:
        """Check if wallet can be debited for given amount"""
        if not self.is_active:
            return False, "Wallet is inactive"
        
        if amount <= 0:
            return False, "Amount must be positive"
        
        if self.balance_cached < amount:
            return False, "Insufficient balance"
        
        # Check daily limit
        if self.daily_limit:
            from datetime import timedelta
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_debits = self.ledger_entries.filter(
                entry_type='debit',
                created_at__gte=today_start
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            if today_debits + amount > self.daily_limit:
                return False, f"Daily limit exceeded ({self.daily_limit} {self.currency})"
        
        return True, ""


class LedgerEntry(models.Model):
    """Double-entry ledger for all wallet transactions"""
    
    ENTRY_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    
    REF_TYPE_CHOICES = [
        ('payment', 'Payment'),
        ('reservation', 'Reservation'),
        ('payout', 'Payout'),
        ('commission', 'Commission'),
        ('refund', 'Refund'),
        ('fee', 'Fee'),
        ('adjustment', 'Manual Adjustment'),
        ('transfer', 'Wallet Transfer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='ledger_entries')
    
    # Entry details
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3)
    
    # Reference to source transaction
    ref_type = models.CharField(max_length=20, choices=REF_TYPE_CHOICES)
    ref_id = models.CharField(max_length=128, help_text="ID of the referenced object")
    
    # Transaction grouping (for double-entry pairs)
    txid = models.UUIDField(default=uuid.uuid4, help_text="Transaction ID for grouping related entries")
    
    # Description and metadata
    description = models.CharField(max_length=500)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_ledger_entries'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['ref_type', 'ref_id']),
            models.Index(fields=['txid']),
            models.Index(fields=['entry_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.amount} {self.currency} - {self.description}"

    @property
    def balance_after(self):
        """Calculate wallet balance after this entry"""
        # Get all entries up to this one
        entries_before = LedgerEntry.objects.filter(
            wallet=self.wallet,
            created_at__lte=self.created_at,
            id__lte=self.id
        ).order_by('created_at', 'id')
        
        balance = Decimal('0.00')
        for entry in entries_before:
            if entry.entry_type == 'credit':
                balance += entry.amount
            else:
                balance -= entry.amount
        
        return balance


class Beneficiary(models.Model):
    """Payout beneficiary information with KYC"""
    
    PAYOUT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('paypal', 'PayPal'),
        ('crypto', 'Cryptocurrency'),
    ]
    
    KYC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='beneficiaries')
    
    # Beneficiary details
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=25, blank=True)
    
    # KYC information
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='pending')
    kyc_documents = models.JSONField(default=dict, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_beneficiaries'
    )
    
    # Payout method configuration
    payout_method = models.CharField(max_length=20, choices=PAYOUT_METHOD_CHOICES)
    payout_details = models.JSONField(
        default=dict,
        help_text="Method-specific details (account numbers, addresses, etc.)"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['owner', 'is_active']),
            models.Index(fields=['kyc_status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_payout_method_display()}) - {self.get_kyc_status_display()}"

    @property
    def can_receive_payouts(self):
        return self.is_active and self.kyc_status == 'verified'

    def save(self, *args, **kwargs):
        # Ensure only one default beneficiary per owner
        if self.is_default:
            Beneficiary.objects.filter(
                owner=self.owner,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
        
        super().save(*args, **kwargs)


class Payout(models.Model):
    """Payout requests and processing"""
    
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='payouts')
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.PROTECT, related_name='payouts')
    
    # Payout details
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3)
    fee_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Status and processing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    provider_ref = models.CharField(max_length=128, blank=True)
    failure_reason = models.TextField(blank=True)
    
    # Approval workflow
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payouts'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Processing timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['beneficiary']),
        ]

    def __str__(self):
        return f"Payout {self.amount} {self.currency} to {self.beneficiary.name} ({self.get_status_display()})"

    @property
    def can_be_cancelled(self):
        return self.status in ['queued', 'processing']

    @property
    def is_completed(self):
        return self.status in ['paid', 'failed', 'cancelled']

    def save(self, *args, **kwargs):
        # Calculate net amount
        self.net_amount = self.amount - self.fee_amount
        super().save(*args, **kwargs)


class WalletTransaction(models.Model):
    """High-level wallet transactions (groups of ledger entries)"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('commission', 'Commission'),
        ('fee', 'Fee'),
        ('adjustment', 'Adjustment'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Involved wallets
    from_wallet = models.ForeignKey(
        Wallet, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='outgoing_transactions'
    )
    to_wallet = models.ForeignKey(
        Wallet, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='incoming_transactions'
    )
    
    # Amount and currency
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3)
    
    # Reference and description
    reference = models.CharField(max_length=128, unique=True)
    description = models.CharField(max_length=500)
    
    # External references
    external_ref = models.CharField(max_length=128, blank=True)
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.CharField(max_length=128, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_wallet', 'status']),
            models.Index(fields=['to_wallet', 'status']),
            models.Index(fields=['transaction_type', 'status']),
            models.Index(fields=['reference']),
            models.Index(fields=['related_object_type', 'related_object_id']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} {self.currency} - {self.reference}"

    @property
    def is_transfer(self):
        return self.from_wallet and self.to_wallet

    @property
    def net_change_for_wallet(self, wallet):
        """Calculate net change for a specific wallet"""
        if wallet == self.from_wallet:
            return -self.amount
        elif wallet == self.to_wallet:
            return self.amount
        return Decimal('0.00')


class PayoutProvider(models.Model):
    """Configuration for payout providers"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    
    # Supported methods and currencies
    supported_methods = models.JSONField(default=list)
    supported_currencies = models.JSONField(default=list)
    
    # Fee structure
    fee_structure = models.JSONField(
        default=dict,
        help_text="Fee calculation rules"
    )
    
    # Limits
    min_payout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    max_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Configuration
    api_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def calculate_fee(self, amount: Decimal, method: str) -> Decimal:
        """Calculate payout fee for given amount and method"""
        fee_config = self.fee_structure.get(method, {})
        
        # Fixed fee
        fixed_fee = Decimal(str(fee_config.get('fixed', 0)))
        
        # Percentage fee
        percentage = Decimal(str(fee_config.get('percentage', 0)))
        percentage_fee = amount * (percentage / 100)
        
        # Minimum fee
        min_fee = Decimal(str(fee_config.get('min', 0)))
        
        # Maximum fee
        max_fee = fee_config.get('max')
        max_fee = Decimal(str(max_fee)) if max_fee else None
        
        total_fee = fixed_fee + percentage_fee
        total_fee = max(total_fee, min_fee)
        
        if max_fee:
            total_fee = min(total_fee, max_fee)
        
        return total_fee

    def supports_method(self, method: str) -> bool:
        return method in self.supported_methods

    def supports_currency(self, currency: str) -> bool:
        return currency in self.supported_currencies