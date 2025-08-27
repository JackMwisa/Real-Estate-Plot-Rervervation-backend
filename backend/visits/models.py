from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()


class VisitSlot(models.Model):
    """Available time slots for property visits"""
    
    TOUR_TYPE_CHOICES = [
        ('onsite', 'On-site Visit'),
        ('virtual', 'Virtual Tour'),
        ('hybrid', 'Hybrid (Both)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        'listings.Listing', 
        on_delete=models.CASCADE, 
        related_name='visit_slots'
    )
    agent = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='agent_slots'
    )
    
    # Schedule
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    
    # Capacity
    capacity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    
    # Tour configuration
    tour_type = models.CharField(max_length=10, choices=TOUR_TYPE_CHOICES, default='onsite')
    virtual_tour_url = models.URLField(blank=True)
    meeting_location = models.CharField(max_length=500, blank=True)
    
    # Fees
    fee_amount = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Optional viewing fee"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Status and notes
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
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
        return f"Visit slot for {self.listing.title} on {self.start_at}"

    @property
    def available_capacity(self):
        """Calculate available capacity"""
        booked_count = self.visits.filter(
            status__in=['confirmed', 'checked_in']
        ).aggregate(
            total=models.Sum('visitor_count')
        )['total'] or 0
        
        return max(0, self.capacity - booked_count)

    @property
    def is_full(self):
        return self.available_capacity <= 0

    @property
    def is_past(self):
        return self.start_at <= timezone.now()

    @property
    def supports_virtual(self):
        return self.tour_type in ['virtual', 'hybrid']

    @property
    def supports_onsite(self):
        return self.tour_type in ['onsite', 'hybrid']


class Visit(models.Model):
    """Individual visit requests and bookings"""
    
    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    TOUR_TYPE_CHOICES = [
        ('onsite', 'On-site Visit'),
        ('virtual', 'Virtual Tour'),
    ]
    
    BOOKING_INTENT_CHOICES = [
        ('viewing', 'Just Viewing'),
        ('interested', 'Interested in Renting'),
        ('serious', 'Serious About Buying'),
        ('comparing', 'Comparing Options'),
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
        related_name='visits'
    )
    slot = models.ForeignKey(
        VisitSlot, 
        on_delete=models.CASCADE, 
        related_name='visits'
    )
    
    # Visit details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    selected_tour_type = models.CharField(max_length=10, choices=TOUR_TYPE_CHOICES, default='onsite')
    booking_intent = models.CharField(max_length=20, choices=BOOKING_INTENT_CHOICES, default='viewing')
    budget_range = models.CharField(max_length=50, blank=True)
    move_in_date = models.DateField(null=True, blank=True)
    
    # Group details
    visitor_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    special_requests = models.TextField(blank=True)
    
    # Payment
    fee_amount = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    currency = models.CharField(max_length=3, default='USD')
    fee_paid = models.BooleanField(default=False)
    payment_reference = models.CharField(max_length=128, blank=True)
    
    # Check-in
    checkin_code = models.CharField(max_length=8, blank=True)
    checkin_at = models.DateTimeField(null=True, blank=True)
    checkin_location = models.JSONField(null=True, blank=True)
    
    # Virtual tour tracking
    virtual_tour_accessed_at = models.DateTimeField(null=True, blank=True)
    virtual_tour_duration = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Duration in seconds"
    )
    
    # Documentation
    proof_photo = models.ImageField(
        upload_to='visit_proofs/%Y/%m/%d/', 
        null=True, 
        blank=True
    )
    
    # Feedback
    buyer_rating = models.PositiveIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    buyer_feedback = models.TextField(blank=True)
    agent_notes = models.TextField(blank=True)
    
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

    def __str__(self):
        return f"Visit by {self.buyer.username} for {self.listing.title}"

    @property
    def can_checkin(self):
        """Check if visit can be checked in"""
        if self.status != 'confirmed':
            return False
        
        now = timezone.now()
        # Allow check-in 15 minutes before start time
        checkin_window_start = self.slot.start_at - timezone.timedelta(minutes=15)
        checkin_window_end = self.slot.end_at
        
        return checkin_window_start <= now <= checkin_window_end

    @property
    def can_access_virtual_tour(self):
        """Check if virtual tour can be accessed"""
        return (
            self.status in ['confirmed', 'checked_in', 'completed'] and
            self.selected_tour_type in ['virtual'] and
            self.slot.virtual_tour_url
        )

    @property
    def is_past_due(self):
        """Check if visit is past due"""
        return self.slot.end_at < timezone.now() and self.status in ['requested', 'confirmed']


class DirectBookingInquiry(models.Model):
    """Direct booking inquiries from completed visits"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('responded', 'Responded'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visit = models.OneToOneField(
        Visit, 
        on_delete=models.CASCADE, 
        related_name='booking_inquiry'
    )
    
    # Inquiry details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    offered_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    currency = models.CharField(max_length=3, default='USD')
    proposed_terms = models.TextField(blank=True)
    buyer_message = models.TextField()
    
    # Agent response
    agent_response = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking inquiry for {self.visit.listing.title}"
    
    
    class VisitReminderTask(models.Model):
    """Scheduled reminders (email/SMS/etc.) for upcoming visits."""

    REMINDER_TYPE_CHOICES = [
        ('email', 'Email Reminder'),
        ('sms', 'SMS Reminder'),
        ('push', 'Push Notification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='reminder_tasks'
    )
    reminder_type = models.CharField(
        max_length=20,
        choices=REMINDER_TYPE_CHOICES,
        default='email'
    )
    scheduled_at = models.DateTimeField(
        help_text="When this reminder should be sent"
    )
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']
        indexes = [
            models.Index(fields=['reminder_type', 'is_sent']),
            models.Index(fields=['scheduled_at']),
        ]

    def __str__(self):
        return f"{self.reminder_type} reminder for Visit {self.visit.id} at {self.scheduled_at}"
