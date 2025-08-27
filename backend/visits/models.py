from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid
import secrets
import string

User = get_user_model()


class VisitSlot(models.Model):
    """Available time slots for property visits"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        'listings.Listing', 
        on_delete=models.CASCADE, 
        related_name='visit_slots'
    )
    agent = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='managed_slots',
        help_text="Agent managing this slot"
    )
    
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Maximum number of visitors for this slot"
    )
    
    # Optional fee for viewing
    fee_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Slot configuration
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Internal notes for the agent")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_at']
        indexes = [
            models.Index(fields=['listing', 'start_at']),
            models.Index(fields=['agent', 'start_at']),
            models.Index(fields=['is_active', 'start_at']),
        ]

    def __str__(self):
        return f"Slot for {self.listing.title} - {self.start_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def is_past(self):
        return timezone.now() > self.end_at

    @property
    def available_capacity(self):
        """Calculate remaining capacity for this slot"""
        confirmed_visits = self.visits.filter(
            status__in=['confirmed', 'checked_in', 'completed']
        ).count()
        return max(0, self.capacity - confirmed_visits)

    @property
    def is_full(self):
        return self.available_capacity == 0

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_at >= self.end_at:
            raise ValidationError("End time must be after start time")
        if self.start_at <= timezone.now():
            raise ValidationError("Start time must be in the future")


class Visit(models.Model):
    """Individual visit requests and bookings"""
    
    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        'listings.Listing', 
        on_delete=models.CASCADE, 
        related_name='visits'
    )
    buyer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='visits',
        help_text="User requesting the visit"
    )
    slot = models.ForeignKey(
        VisitSlot, 
        on_delete=models.CASCADE, 
        related_name='visits'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    
    # Visit details
    visitor_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Number of people attending"
    )
    special_requests = models.TextField(
        blank=True,
        help_text="Special requests or notes from buyer"
    )
    
    # Fee handling
    fee_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    currency = models.CharField(max_length=3, default='USD')
    fee_paid = models.BooleanField(default=False)
    payment_reference = models.CharField(max_length=255, blank=True)
    
    # Check-in system
    checkin_code = models.CharField(
        max_length=8, 
        blank=True,
        help_text="6-digit code for check-in verification"
    )
    checkin_at = models.DateTimeField(null=True, blank=True)
    checkin_location = models.JSONField(
        default=dict, 
        blank=True,
        help_text="GPS coordinates for check-in verification"
    )
    
    # Proof and feedback
    proof_photo = models.ImageField(
        upload_to='visit_proofs/%Y/%m/%d/', 
        null=True, 
        blank=True,
        help_text="Photo proof of visit"
    )
    buyer_rating = models.PositiveIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Buyer rating of the visit (1-5)"
    )
    buyer_feedback = models.TextField(blank=True)
    agent_notes = models.TextField(
        blank=True,
        help_text="Private notes from agent"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['listing', 'status']),
            models.Index(fields=['slot', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        unique_together = ['buyer', 'slot']  # One visit per buyer per slot

    def __str__(self):
        return f"Visit by {self.buyer.username} - {self.listing.title} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Generate check-in code if confirmed and not already set
        if self.status == 'confirmed' and not self.checkin_code:
            self.checkin_code = self.generate_checkin_code()
        
        # Set timestamps based on status changes
        if self.status == 'confirmed' and not self.confirmed_at:
            self.confirmed_at = timezone.now()
        elif self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)

    @staticmethod
    def generate_checkin_code():
        """Generate a 6-digit alphanumeric check-in code"""
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

    @property
    def can_checkin(self):
        """Check if visit can be checked in"""
        if self.status != 'confirmed':
            return False
        
        now = timezone.now()
        slot_start = self.slot.start_at
        slot_end = self.slot.end_at
        
        # Allow check-in 15 minutes before slot starts until slot ends
        checkin_window_start = slot_start - timezone.timedelta(minutes=15)
        
        return checkin_window_start <= now <= slot_end

    @property
    def is_past_due(self):
        """Check if visit is past due for check-in"""
        return (
            self.status == 'confirmed' and 
            timezone.now() > self.slot.end_at
        )

    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Check slot capacity
        if self.visitor_count > self.slot.available_capacity:
            raise ValidationError("Not enough capacity in the selected slot")
        
        # Check if slot is in the future
        if self.slot.start_at <= timezone.now():
            raise ValidationError("Cannot book visits for past time slots")


class VisitReminderTask(models.Model):
    """Track reminder notifications for visits"""
    
    REMINDER_TYPE_CHOICES = [
        ('24h_before', '24 Hours Before'),
        ('2h_before', '2 Hours Before'),
        ('checkin_available', 'Check-in Available'),
    ]

    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES)
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    is_sent = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['visit', 'reminder_type']
        indexes = [
            models.Index(fields=['scheduled_at', 'is_sent']),
        ]

    def __str__(self):
        return f"Reminder for {self.visit} - {self.get_reminder_type_display()}"