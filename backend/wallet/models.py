from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()


class Wallet(models.Model):
    """User or Agency wallet for holding funds"""
    
    WALLET_TYPE_CHOICES = [
        ('user', 'User Wallet'),
        ('agency', 'Agency Wallet'),
        ('escrow', 'Escrow Wallet'),
        ('platform', 'Platform Wallet'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Ownership (one of these will be set)
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
    
    wallet_type = models.CharField(max_length=20, choices=WALLET_TYPE_CHOICES, default='user')
    
    # Balance and currency
    balance_cached = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Security and limits
    is_active = models.BooleanField(default=True)
    is_frozen = models.BooleanField(default=False)
    freeze_reason = models.CharField(max_length=200, blank=True)
    
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
    
    # Security settings
    requires_2fa = models.BooleanField(default=False)
    pin_hash = models.CharField(max_length=128, blank=True)
    
    # Activity tracking
    last_activity_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner_user']),
            models.Index(fields=['owner_agency']),
            models.Index(fields=['wallet_type', 'is_active']),
            models.Index(fields=['currency']),
        ]

    def __str__(self):
        return f"{self.get_wallet_type_display()} - {self.get_owner_display()}"

    def get_owner_display(self):
        if self.owner_user:
            return self.owner_user.username
        elif self.owner_agency:
            return self.owner_agency.agency_name or f"Agency {self.owner_agency.id}"
        return f"Wallet {self.id}"

    def get_owner(self):
        """Get the actual owner object"""
        return self.owner_user or self.owner_agency

    @property
    def calculated_balance(self):
        """Calculate balance from ledger entries"""
        from django.db.models import Sum, Q
        
        credits = self.ledger_entries.filter(entry_type='credit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        debits = self.ledger_entries.filter(entry_type='debit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        return credits - debits

    def refresh_balance(self):
        """Refresh cached balance from ledger"""
        self.balance_cached = self.calculated_balance
        self.save(update_fields=['balance_cached'])

    def can_debit(self, amount):
        """Check if wallet can be debited by amount"""
        if not self.is_active:
            return False, "Wallet is inactive"
        
        if self.is_frozen:
            return False, f"Wallet is frozen: {self.freeze_reason}"
        
        if amount > self.balance_cached:
            return False, "Insufficient balance"
        
        # Check daily limit
        if self.daily_limit:
            from datetime import timedelta
            today = timezone.now().date()
            daily_spent = self.ledger_entries.filter(
                entry_type='debit',
                created_at__date=today
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            if daily_spent + amount > self.daily_limit:
                return False, "Daily limit exceeded"
        
        # Check monthly limit
        if self.monthly_limit:
            from datetime import timedelta
            month_start = timezone.now().replace(day=1)
            monthly_spent = self.ledger_entries.filter(
                entry_type='debit',
                created_at__gte=month_start
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            if monthly_spent + amount > self.monthly_limit:
                return False, "Monthly limit exceeded"
        
        return True, None


class CurrencyExchangeRate(models.Model):
    """Exchange rates for multi-currency support"""
    
    PROVIDER_CHOICES = [
        ('manual', 'Manual Entry'),
        ('xe', 'XE.com'),
        ('fixer', 'Fixer.io'),
        ('openexchange', 'Open Exchange Rates'),
    ]

    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='manual')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['from_currency', 'to_currency', 'provider']
        indexes = [
            models.Index(fields=['from_currency', 'to_currency']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.from_currency}/{self.to_currency}: {self.rate}"

    @property
    def is_expired(self):
        return self.expires_at and timezone.now() > self.expires_at


class CommissionRule(models.Model):
    """Rules for calculating commissions and fees"""
    
    RULE_TYPE_CHOICES = [
        ('platform_fee', 'Platform Fee'),
        ('agent_commission', 'Agent Commission'),
        ('referral_bonus', 'Referral Bonus'),
        ('listing_fee', 'Listing Fee'),
        ('transaction_fee', 'Transaction Fee'),
    ]
    
    APPLIES_TO_CHOICES = [
        ('all', 'All Transactions'),
        ('reservations', 'Reservations'),
        ('payments', 'Payments'),
        ('payouts', 'Payouts'),
        ('listings', 'Listings'),
    ]

    name = models.CharField(max_length=100)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    applies_to = models.CharField(max_length=20, choices=APPLIES_TO_CHOICES, default='all')
    
    # Commission calculation
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))]
    )
    fixed_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Tiered structure (JSON)
    tiered_structure = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tiered commission structure based on amount ranges"
    )
    
    # Conditions
    min_transaction_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    max_transaction_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    target_conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional conditions for rule application"
    )
    
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"

    def calculate_commission(self, amount):
        """Calculate commission for given amount"""
        if self.min_transaction_amount and amount < self.min_transaction_amount:
            return Decimal('0.00')
        
        if self.max_transaction_amount and amount > self.max_transaction_amount:
            return Decimal('0.00')
        
        # Fixed amount
        if self.fixed_amount:
            return self.fixed_amount
        
        # Percentage
        if self.percentage:
            return amount * (self.percentage / Decimal('100'))
        
        # Tiered structure
        if self.tiered_structure:
            for tier in self.tiered_structure.get('tiers', []):
                min_amount = Decimal(str(tier.get('min_amount', 0)))
                max_amount = Decimal(str(tier.get('max_amount', float('inf'))))
                
                if min_amount <= amount <= max_amount:
                    if tier.get('percentage'):
                        return amount * (Decimal(str(tier['percentage'])) / Decimal('100'))
                    elif tier.get('fixed_amount'):
                        return Decimal(str(tier['fixed_amount']))
        
        return Decimal('0.00')


class SavingsGoal(models.Model):
    """User savings goals"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='savings_goals')
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3)
    
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Auto-save settings
    auto_save_enabled = models.BooleanField(default=False)
    auto_save_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    auto_save_frequency = models.CharField(
        max_length=10, 
        choices=FREQUENCY_CHOICES, 
        null=True, 
        blank=True
    )
    last_auto_save = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.current_amount}/{self.target_amount} {self.currency}"

    @property
    def progress_percentage(self):
        if self.target_amount <= 0:
            return 0.0
        return float(self.current_amount / self.target_amount * 100)

    @property
    def is_completed(self):
        return self.current_amount >= self.target_amount


class SecurityAlert(models.Model):
    """Security alerts for suspicious wallet activity"""
    
    ALERT_TYPE_CHOICES = [
        ('large_transaction', 'Large Transaction'),
        ('unusual_pattern', 'Unusual Pattern'),
        ('multiple_failures', 'Multiple Failed Attempts'),
        ('new_device', 'New Device Access'),
        ('location_change', 'Location Change'),
        ('rapid_transactions', 'Rapid Transactions'),
    ]
    
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='security_alerts')
    
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    alert_data = models.JSONField(default=dict, blank=True)
    
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_security_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'is_resolved']),
            models.Index(fields=['alert_type', 'severity']),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.wallet.get_owner_display()}"


class LedgerEntry(models.Model):
    """Immutable double-entry ledger entries"""
    
    ENTRY_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='ledger_entries')
    
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    
    # Reference to source transaction
    ref_type = models.CharField(max_length=50, help_text="Type of transaction (payment, transfer, etc.)")
    ref_id = models.CharField(max_length=128, help_text="ID of the source transaction")
    txid = models.UUIDField(help_text="Transaction ID for grouping related entries")
    
    description = models.CharField(max_length=500)
    
    # Running balance after this entry
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Metadata for additional context
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['ref_type', 'ref_id']),
            models.Index(fields=['txid']),
            models.Index(fields=['entry_type', 'currency']),
        ]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.amount} {self.currency} - {self.wallet.get_owner_display()}"


class Beneficiary(models.Model):
    """KYC-verified payout recipients"""
    
    KYC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    PAYOUT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('paypal', 'PayPal'),
        ('crypto', 'Cryptocurrency'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='beneficiaries')
    
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=25, blank=True)
    
    # KYC information
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='pending')
    kyc_documents = models.JSONField(default=dict, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Payout details
    payout_method = models.CharField(max_length=20, choices=PAYOUT_METHOD_CHOICES)
    payout_details = models.JSONField(
        default=dict,
        help_text="Method-specific payout details (account numbers, addresses, etc.)"
    )
    
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
        return f"{self.name} ({self.get_payout_method_display()})"

    @property
    def can_receive_payouts(self):
        return self.is_active and self.kyc_status == 'verified'


class Payout(models.Model):
    """Payout requests from wallets to beneficiaries"""
    
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
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['beneficiary', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Payout {self.amount} {self.currency} to {self.beneficiary.name}"

    @property
    def can_be_cancelled(self):
        return self.status in ['queued', 'processing']

    @property
    def is_completed(self):
        return self.status in ['paid', 'failed', 'cancelled']


class WalletTransaction(models.Model):
    """High-level transaction grouping for transfers and complex operations"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('transfer', 'Wallet Transfer'),
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('commission', 'Commission'),
        ('fee', 'Fee'),
        ('escrow_hold', 'Escrow Hold'),
        ('escrow_release', 'Escrow Release'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    
    # Wallets involved
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
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    reference = models.CharField(max_length=128, unique=True)
    description = models.CharField(max_length=500)
    external_ref = models.CharField(max_length=128, blank=True)
    
    # Link to related objects
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.CharField(max_length=128, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_wallet', 'status']),
            models.Index(fields=['to_wallet', 'status']),
            models.Index(fields=['reference']),
            models.Index(fields=['related_object_type', 'related_object_id']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} {self.currency}"

    @property
    def is_transfer(self):
        return self.from_wallet and self.to_wallet


class PayoutProvider(models.Model):
    """Configuration for payout providers"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    
    supported_methods = models.JSONField(
        default=list,
        help_text="List of supported payout methods"
    )
    supported_currencies = models.JSONField(
        default=list,
        help_text="List of supported currencies"
    )
    
    fee_structure = models.JSONField(
        default=dict,
        help_text="Fee calculation structure"
    )
    
    min_payout_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('1.00')
    )
    max_payout_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class WalletAnalytics(models.Model):
    """Daily analytics rollup for wallets"""
    
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='analytics')
    date = models.DateField()
    
    # Daily metrics
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    total_credits = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_debits = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    transaction_count = models.PositiveIntegerField(default=0)
    largest_transaction = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['wallet', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"Analytics {self.wallet.get_owner_display()} - {self.date}"


class InvestmentPool(models.Model):
    """Investment pools for property investments"""
    
    STATUS_CHOICES = [
        ('open', 'Open for Investment'),
        ('funding', 'Funding in Progress'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField()
    
    # Investment details
    target_amount = models.DecimalField(max_digits=15, decimal_places=2)
    current_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='USD')
    
    min_investment = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('100.00'))
    max_investment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Returns
    expected_return_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    investment_period_months = models.PositiveIntegerField(default=12)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Related property
    listing = models.ForeignKey(
        'listings.Listing',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='investment_pools'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    funding_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.current_amount}/{self.target_amount} {self.currency}"

    @property
    def funding_percentage(self):
        if self.target_amount <= 0:
            return 0.0
        return float(self.current_amount / self.target_amount * 100)

    @property
    def is_fully_funded(self):
        return self.current_amount >= self.target_amount


class Investment(models.Model):
    """Individual investments in pools"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pool = models.ForeignKey(InvestmentPool, on_delete=models.CASCADE, related_name='investments')
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investments')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    
    # Returns tracking
    returns_earned = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    last_return_payment = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['pool', 'investor']

    def __str__(self):
        return f"{self.investor.username} - {self.amount} {self.currency} in {self.pool.name}"

    @property
    def roi_percentage(self):
        if self.amount <= 0:
            return 0.0
        return float(self.returns_earned / self.amount * 100)