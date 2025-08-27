from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()


class AdPackage(models.Model):
    """Available advertising packages with pricing and features"""
    
    PRICING_MODEL_CHOICES = [
        ('flat', 'Flat Rate'),
        ('cpm', 'Cost Per Mille (CPM)'),
        ('cpc', 'Cost Per Click (CPC)'),
    ]
    
    GEO_SCOPE_CHOICES = [
        ('global', 'Global'),
        ('country', 'Country'),
        ('region', 'Region'),
        ('city', 'City'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    duration_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(365)]
    )
    pricing_model = models.CharField(max_length=10, choices=PRICING_MODEL_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency = models.CharField(max_length=3, default='USD')
    
    geo_scope = models.CharField(max_length=20, choices=GEO_SCOPE_CHOICES, default='global')
    max_boost_score = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(10.0)],
        help_text="Maximum boost multiplier for search ranking"
    )
    
    # Package features
    featured_placement = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    analytics_access = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']
        indexes = [
            models.Index(fields=['is_active', 'geo_scope']),
            models.Index(fields=['pricing_model']),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_performance_based(self):
        return self.pricing_model in ['cpm', 'cpc']


class AdCampaign(models.Model):
    """User advertising campaigns for listings or agencies"""
    
    TARGET_TYPE_CHOICES = [
        ('listing', 'Listing'),
        ('agency', 'Agency'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_campaigns')
    package = models.ForeignKey(AdPackage, on_delete=models.PROTECT, related_name='campaigns')
    
    # Campaign targeting
    target_type = models.CharField(max_length=10, choices=TARGET_TYPE_CHOICES)
    target_id = models.PositiveIntegerField(help_text="ID of the listing or agency being promoted")
    
    # Campaign schedule
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    
    # Budget and performance
    budget = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    spent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    boost_score = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(10.0)]
    )
    
    # Metrics (updated by background jobs)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    
    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='approved_campaigns'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'start_at', 'end_at']),
            models.Index(fields=['target_type', 'target_id']),
        ]

    def __str__(self):
        return f"Campaign {self.id} - {self.get_target_type_display()} {self.target_id}"

    @property
    def is_active(self):
        now = timezone.now()
        return (
            self.status == 'active' and
            self.start_at <= now <= self.end_at and
            self.spent_amount < self.budget
        )

    @property
    def ctr(self):
        """Click-through rate as percentage"""
        if self.impressions == 0:
            return 0.0
        return (self.clicks / self.impressions) * 100

    @property
    def cost_per_click(self):
        """Average cost per click"""
        if self.clicks == 0:
            return Decimal('0.00')
        return self.spent_amount / self.clicks

    @property
    def cost_per_impression(self):
        """Cost per thousand impressions (CPM)"""
        if self.impressions == 0:
            return Decimal('0.00')
        return (self.spent_amount / self.impressions) * 1000

    def can_serve_ad(self):
        """Check if campaign can serve ads right now"""
        return (
            self.is_active and
            self.spent_amount < self.budget
        )

    def get_target_object(self):
        """Get the actual target object (listing or agency profile)"""
        if self.target_type == 'listing':
            from listings.models import Listing
            try:
                return Listing.objects.get(id=self.target_id)
            except Listing.DoesNotExist:
                return None
        elif self.target_type == 'agency':
            from users.models import Profile
            try:
                return Profile.objects.get(id=self.target_id)
            except Profile.DoesNotExist:
                return None
        return None


class AdImpression(models.Model):
    """Track ad impressions for analytics and billing"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='impression_events')
    
    # User context
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=128, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Context
    page_url = models.URLField(blank=True)
    search_query = models.CharField(max_length=500, blank=True)
    position = models.PositiveIntegerField(null=True, blank=True, help_text="Position in search results")
    
    # Billing
    cost = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0.0000'))
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]

    def __str__(self):
        return f"Impression {self.id} - Campaign {self.campaign_id}"


class AdClick(models.Model):
    """Track ad clicks for analytics and billing"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='click_events')
    impression = models.OneToOneField(
        AdImpression, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='click'
    )
    
    # User context
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=128, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Click details
    clicked_url = models.URLField()
    referrer_url = models.URLField(blank=True)
    
    # Billing
    cost = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0.0000'))
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]

    def __str__(self):
        return f"Click {self.id} - Campaign {self.campaign_id}"


class AdMetricsRollup(models.Model):
    """Daily rollup of campaign metrics for performance"""
    
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField()
    
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    spend = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['campaign', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['campaign', 'date']),
        ]

    def __str__(self):
        return f"Metrics {self.campaign_id} - {self.date}"

    @property
    def ctr(self):
        if self.impressions == 0:
            return 0.0
        return (self.clicks / self.impressions) * 100

    @property
    def cpc(self):
        if self.clicks == 0:
            return Decimal('0.00')
        return self.spend / self.clicks