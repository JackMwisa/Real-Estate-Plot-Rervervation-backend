from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()


class Reservation(models.Model):
    """Escrow-backed reservations for listings"""
    
    ESCROW_STATE_CHOICES = [
        ('initiated', 'Initiated'),
        ('paid', 'Paid'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
        ('released', 'Released'),
        ('disputed', 'Disputed'),
        ('cancelled', 'Cancelled'),
    ]
    
    RESERVATION_TYPE_CHOICES = [
        ('rental', 'Rental'),
        ('purchase', 'Purchase'),
        ('short_stay', 'Short Stay'),
        ('viewing_fee', 'Viewing Fee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core relationships
    listing = models.ForeignKey(
        'listings.Listing', 
        on_delete=models.CASCADE, 
        related_name='reservations'
    )
    buyer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='reservations'
    )
    
    # Optional visit connection
    visit = models.OneToOneField(
        'visits.Visit',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservation'
    )
    
    # Reservation details
    reservation_type = models.CharField(
        max_length=20, 
        choices=RESERVATION_TYPE_CHOICES,
        default='rental'
    )
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    
    # Financial details
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    security_deposit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # Escrow state management
    escrow_state = models.CharField(
        max_length=20, 
        choices=ESCROW_STATE_CHOICES, 
        default='initiated'
    )
    escrow_reference = models.CharField(max_length=128, blank=True)
    
    # Policy and terms
    policy = models.JSONField(
        default=dict,
        help_text="Cancellation policy, terms, and conditions"
    )
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    
    # Cancellation
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_reservations'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Key dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['buyer', 'escrow_state']),
            models.Index(fields=['listing', 'escrow_state']),
            models.Index(fields=['escrow_state', 'created_at']),
            models.Index(fields=['start_at', 'end_at']),
        ]

    def __str__(self):
        return f"Reservation {self.id} - {self.listing.title} ({self.get_escrow_state_display()})"

    @property
    def is_active(self):
        """Check if reservation is currently active"""
        return self.escrow_state in ['paid', 'confirmed'] and self.start_at and self.end_at and self.start_at <= timezone.now() <= self.end_at

    @property
    def is_pending(self):
        """Check if reservation is pending payment or confirmation"""
        return self.escrow_state in ['initiated', 'paid']

    @property
    def is_completed(self):
        """Check if reservation is completed"""
        return self.escrow_state in ['completed', 'released']

    @property
    def can_cancel(self):
        """Check if reservation can be cancelled"""
        return self.escrow_state in ['initiated', 'paid', 'confirmed']

    @property
    def can_dispute(self):
        """Check if reservation can be disputed"""
        return self.escrow_state in ['confirmed', 'completed']

    @property
    def total_amount(self):
        """Total amount including security deposit"""
        return self.amount + self.security_deposit

    def get_cancellation_policy(self):
        """Get cancellation policy from policy JSON"""
        return self.policy.get('cancellation', {})

    def calculate_refund_amount(self):
        """Calculate refund amount based on policy and timing"""
        if self.escrow_state not in ['paid', 'confirmed']:
            return Decimal('0.00')
        
        policy = self.get_cancellation_policy()
        if not policy:
            return self.total_amount
        
        # Simple policy implementation
        if self.start_at and timezone.now() < self.start_at:
            # Before start date
            days_before = (self.start_at - timezone.now()).days
            
            if days_before >= policy.get('full_refund_days', 7):
                return self.total_amount
            elif days_before >= policy.get('partial_refund_days', 3):
                refund_percent = policy.get('partial_refund_percent', 50)
                return self.total_amount * Decimal(str(refund_percent / 100))
            else:
                return Decimal('0.00')
        else:
            # After start date - no refund by default
            return Decimal('0.00')


class DisputeCase(models.Model):
    """Dispute resolution for reservations"""
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('awaiting_response', 'Awaiting Response'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    DISPUTE_TYPE_CHOICES = [
        ('property_condition', 'Property Condition'),
        ('no_show', 'No Show'),
        ('misrepresentation', 'Misrepresentation'),
        ('payment_issue', 'Payment Issue'),
        ('policy_violation', 'Policy Violation'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reservation = models.ForeignKey(
        Reservation, 
        on_delete=models.CASCADE, 
        related_name='disputes'
    )
    
    # Dispute details
    dispute_type = models.CharField(max_length=30, choices=DISPUTE_TYPE_CHOICES)
    opener = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='opened_disputes'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Content
    title = models.CharField(max_length=200)
    description = models.TextField()
    evidence_json = models.JSONField(
        default=dict,
        help_text="Evidence files, screenshots, messages, etc."
    )
    
    # Resolution
    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_disputes'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Financial resolution
    refund_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    compensation_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Priority and assignment
    priority = models.CharField(
        max_length=10,
        choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High')],
        default='normal'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_disputes',
        limit_choices_to={'is_staff': True}
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reservation', 'status']),
            models.Index(fields=['opener', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['status', 'priority']),
        ]

    def __str__(self):
        return f"Dispute {self.id} - {self.title} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status in ['open', 'investigating', 'awaiting_response']

    @property
    def is_resolved(self):
        return self.status in ['resolved', 'closed']

    def can_be_resolved_by(self, user):
        """Check if user can resolve this dispute"""
        return user.is_staff or user == self.assigned_to


class ReservationPolicy(models.Model):
    """Reusable reservation policies"""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Cancellation policy
    full_refund_days = models.PositiveIntegerField(
        default=7,
        help_text="Days before start for full refund"
    )
    partial_refund_days = models.PositiveIntegerField(
        default=3,
        help_text="Days before start for partial refund"
    )
    partial_refund_percent = models.PositiveIntegerField(
        default=50,
        help_text="Percentage refund for partial refund period"
    )
    
    # Security deposit
    security_deposit_percent = models.PositiveIntegerField(
        default=0,
        help_text="Security deposit as percentage of reservation amount"
    )
    security_deposit_fixed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Fixed security deposit amount"
    )
    
    # Terms
    terms_and_conditions = models.TextField(blank=True)
    requires_verification = models.BooleanField(
        default=False,
        help_text="Require verified listing for this policy"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def calculate_security_deposit(self, reservation_amount):
        """Calculate security deposit for given reservation amount"""
        if self.security_deposit_fixed > 0:
            return self.security_deposit_fixed
        
        if self.security_deposit_percent > 0:
            return reservation_amount * Decimal(str(self.security_deposit_percent / 100))
        
        return Decimal('0.00')

    def to_policy_json(self):
        """Convert to JSON format for Reservation.policy field"""
        return {
            'cancellation': {
                'full_refund_days': self.full_refund_days,
                'partial_refund_days': self.partial_refund_days,
                'partial_refund_percent': self.partial_refund_percent,
            },
            'security_deposit': {
                'percent': self.security_deposit_percent,
                'fixed': float(self.security_deposit_fixed),
            },
            'terms': self.terms_and_conditions,
            'requires_verification': self.requires_verification,
        }