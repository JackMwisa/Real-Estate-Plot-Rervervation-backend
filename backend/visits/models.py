    selected_tour_type = models.CharField(
        max_length=20, 
        choices=SELECTED_TOUR_TYPE_CHOICES,
        default='onsite',
        help_text="User's preferred tour type"
    )
    
    # Booking intent
    booking_intent = models.CharField(
        max_length=20,
        choices=BOOKING_INTENT_CHOICES,
        default='viewing_only',
        help_text="User's intent for the property"
    )
    budget_range = models.CharField(
        max_length=100,
        blank=True,
        help_text="User's budget range for rent/purchase"
    )
    move_in_date = models.DateField(
        null=True,
        blank=True,
        help_text="Desired move-in date"
    )
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from ..models import VisitSlot, Visit, VisitReminderTask, DirectBookingInquiry

User = get_user_model()


class VisitSlotSerializer(serializers.ModelSerializer):
    agent_username = serializers.CharField(source='agent.username', read_only=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    available_capacity = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    is_past = serializers.ReadOnlyField()
    
    class Meta:
        model = VisitSlot
        fields = [
            'id', 'listing', 'listing_title', 'agent', 'agent_username',
            'fee_amount', 'currency', 'is_active', 'notes', 'is_past',
            'created_at', 'updated_at'
        ]
    # Tour type configuration
    tour_type = models.CharField(
        max_length=20, 
        choices=TOUR_TYPE_CHOICES, 
        default='onsite',
        help_text="Type of tour offered in this slot"
    )
    virtual_tour_url = models.URLField(
        blank=True, 
        null=True,
        help_text="URL for virtual tour (if tour_type includes virtual)"
    )
    meeting_location = models.TextField(
    
    # Virtual tour access
    virtual_tour_accessed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When user accessed virtual tour"
    )
    virtual_tour_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time spent in virtual tour (seconds)"
    )
        blank=True,
        help_text="Meeting point for onsite tours"
    )
    
        read_only_fields = ['id', 'agent', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('start_at') and data.get('end_at'):
            if data['start_at'] >= data['end_at']:
                raise serializers.ValidationError("End time must be after start time")
            
            if data['start_at'] <= timezone.now():
                raise serializers.ValidationError("Start time must be in the future")
        
        return data

    def create(self, validated_data):
        # Set agent to current user
        validated_data['agent'] = self.context['request'].user
        return super().create(validated_data)


class VisitSerializer(serializers.ModelSerializer):
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    agent_username = serializers.CharField(source='slot.agent.username', read_only=True)
    slot_time = serializers.SerializerMethodField()
    can_checkin = serializers.ReadOnlyField()
    is_past_due = serializers.ReadOnlyField()
    
    class Meta:
        model = Visit
        fields = [
            models.Index(fields=['booking_intent']),
            models.Index(fields=['selected_tour_type']),
            'id', 'listing', 'listing_title', 'buyer', 'buyer_username',
            'slot', 'slot_time', 'agent_username', 'status', 'visitor_count',
            'special_requests', 'fee_amount', 'currency', 'fee_paid',
            'payment_reference', 'checkin_code', 'checkin_at', 'checkin_location',
        return f"{self.get_selected_tour_type_display()} by {self.buyer.username} - {self.listing.title} ({self.get_status_display()})"
            'can_checkin', 'is_past_due', 'created_at', 'updated_at',
            'confirmed_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'buyer', 'checkin_code', 'checkin_at', 'created_at',
            'updated_at', 'confirmed_at', 'completed_at'
        ]

    def get_slot_time(self, obj):
        return {
            'start_at': obj.slot.start_at,
            'end_at': obj.slot.end_at
        }

    def validate_slot(self, value):
        # Check if slot has available capacity
        if value.available_capacity < 1:
            raise serializers.ValidationError("This time slot is fully booked")
        
        # Check if slot is in the future
        if value.start_at <= timezone.now():
            raise serializers.ValidationError("Cannot book visits for past time slots")
        
        return value
        
        # Virtual tours don't need physical check-in
        if self.selected_tour_type == 'virtual':
            return False

    def validate_visitor_count(self, value):
            models.Index(fields=['tour_type']),
        if hasattr(self, 'initial_data') and 'slot' in self.initial_data:
            try:
                slot = VisitSlot.objects.get(id=self.initial_data['slot'])
        return f"{self.get_tour_type_display()} for {self.listing.title} - {self.start_at.strftime('%Y-%m-%d %H:%M')}"
                if value > slot.available_capacity:
                        f"Visitor count exceeds available capacity ({slot.available_capacity})"
    
    @property
    def can_access_virtual_tour(self):
        """Check if user can access virtual tour"""
        return (
            self.status == 'confirmed' and
            self.selected_tour_type == 'virtual' and
            self.slot.supports_virtual
        )
                    )
            except VisitSlot.DoesNotExist:
                pass
        
        return value

    def create(self, validated_data):
        # Set buyer to current user
        validated_data['buyer'] = self.context['request'].user
        
        # Set fee amount from slot if applicable
        slot = validated_data['slot']
        if slot.fee_amount:
            validated_data['fee_amount'] = slot.fee_amount
            validated_data['currency'] = slot.currency
    
        
    @property
        return super().create(validated_data)
    def supports_virtual(self):

        return self.tour_type in ['virtual', 'hybrid']

    
class VisitCreateSerializer(serializers.ModelSerializer):
    @property
    """Simplified serializer for creating visits"""
    def supports_onsite(self):
    
        return self.tour_type in ['onsite', 'hybrid']
    class Meta:
        model = Visit
        fields = [
            'slot', 'visitor_count', 'special_requests'
        ]

    def validate_slot(self, value):
        # Check if user already has a visit for this slot
        
        user = self.context['request'].user
        # Validate virtual tour URL if needed
        if Visit.objects.filter(buyer=user, slot=value).exists():
        if self.tour_type in ['virtual', 'hybrid'] and not self.virtual_tour_url:
            raise serializers.ValidationError("You already have a visit booked for this slot")
            raise ValidationError("Virtual tour URL is required for virtual/hybrid tours")
        
        # Check slot availability
        if value.available_capacity < 1:
            raise serializers.ValidationError("This time slot is fully booked")
        
        if value.start_at <= timezone.now():
            raise serializers.ValidationError("Cannot book visits for past time slots")
        
        return value


        
        # Validate tour type compatibility
        if self.selected_tour_type == 'virtual' and not self.slot.supports_virtual:
            raise ValidationError("This slot does not support virtual tours")
        elif self.selected_tour_type == 'onsite' and not self.slot.supports_onsite:
            raise ValidationError("This slot does not support onsite tours")
class VisitCheckinSerializer(serializers.Serializer):
    """Serializer for visit check-in"""
class DirectBookingInquiry(models.Model):
    """Direct booking inquiries from visits"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('contacted', 'Agent Contacted'),
        ('negotiating', 'Negotiating'),
        ('agreement_reached', 'Agreement Reached'),
        ('completed', 'Completed'),
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
        blank=True,
        help_text="Amount offered by buyer"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Terms
    proposed_terms = models.JSONField(
        default=dict,
        blank=True,
        help_text="Proposed rental/purchase terms"
    )
    
    # Communication
    buyer_message = models.TextField(
        blank=True,
        help_text="Message from buyer to agent"
    )
    agent_response = models.TextField(
        blank=True,
        help_text="Response from agent"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this inquiry expires"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['visit']),
        ]
    
    def __str__(self):
        return f"Booking inquiry for {self.visit.listing.title} by {self.visit.buyer.username}"
    
    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    
    SELECTED_TOUR_TYPE_CHOICES = [
    checkin_code = serializers.CharField(max_length=8)
        ('onsite', 'Onsite Physical Tour'),
    location = serializers.JSONField(required=False)
        ('virtual', 'Virtual Tour'),
    proof_photo = serializers.ImageField(required=False)
        ('virtual_tour_ready', 'Virtual Tour Ready'),
    ]

    
    def validate_checkin_code(self, value):
    BOOKING_INTENT_CHOICES = [
        visit = self.context['visit']
        ('viewing_only', 'Viewing Only'),
        if visit.checkin_code != value.upper():
        ('rent_daily', 'Rent Daily'),
            raise serializers.ValidationError("Invalid check-in code")
        ('rent_weekly', 'Rent Weekly'), 
        return value.upper()
        ('rent_monthly', 'Rent Monthly'),

        ('rent_yearly', 'Rent Yearly'),

        ('purchase', 'Purchase'),
class VisitFeedbackSerializer(serializers.Serializer):
        ('lease_to_own', 'Lease to Own'),
    """Serializer for visit feedback"""
    ]
    
    rating = serializers.IntegerField(min_value=1, max_value=5)
    feedback = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class VisitReminderTaskSerializer(serializers.ModelSerializer):
    visit_details = serializers.SerializerMethodField()
    
    class Meta:
        model = VisitReminderTask
        fields = [
            'id', 'visit', 'visit_details', 'reminder_type', 'scheduled_at',
            'sent_at', 'is_sent', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_visit_details(self, obj):
        return {
            'id': str(obj.visit.id),
            'listing_title': obj.visit.listing.title,
            'buyer_username': obj.visit.buyer.username,
    
            'slot_time': obj.visit.slot.start_at
    # Tour preference
        }