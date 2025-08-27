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
            'tour_type', 'virtual_tour_url', 'meeting_location',
            'start_at', 'end_at', 'capacity', 'available_capacity', 'is_full',
            'fee_amount', 'currency', 'is_active', 'notes', 'is_past',
            'supports_virtual', 'supports_onsite', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'agent', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('start_at') and data.get('end_at'):
            if data['start_at'] >= data['end_at']:
                raise serializers.ValidationError("End time must be after start time")
            
            if data['start_at'] <= timezone.now():
                raise serializers.ValidationError("Start time must be in the future")
        
        # Validate virtual tour URL for virtual/hybrid tours
        tour_type = data.get('tour_type')
        virtual_tour_url = data.get('virtual_tour_url')
        
        if tour_type in ['virtual', 'hybrid'] and not virtual_tour_url:
            raise serializers.ValidationError("Virtual tour URL is required for virtual/hybrid tours")
        
        return data

    def create(self, validated_data):
        # Set agent to current user
        validated_data['agent'] = self.context['request'].user
        return super().create(validated_data)


class DirectBookingInquirySerializer(serializers.ModelSerializer):
    visit_details = serializers.SerializerMethodField()
    listing_title = serializers.CharField(source='visit.listing.title', read_only=True)
    buyer_username = serializers.CharField(source='visit.buyer.username', read_only=True)
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = DirectBookingInquiry
        fields = [
            'id', 'visit', 'visit_details', 'listing_title', 'buyer_username',
            'status', 'offered_amount', 'currency', 'proposed_terms',
            'buyer_message', 'agent_response', 'is_expired',
            'created_at', 'updated_at', 'responded_at', 'expires_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_visit_details(self, obj):
        return {
            'id': str(obj.visit.id),
            'booking_intent': obj.visit.booking_intent,
            'budget_range': obj.visit.budget_range,
            'move_in_date': obj.visit.move_in_date,
            'selected_tour_type': obj.visit.selected_tour_type
        }
class VisitSerializer(serializers.ModelSerializer):
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    agent_username = serializers.CharField(source='slot.agent.username', read_only=True)
    slot_time = serializers.SerializerMethodField()
    can_checkin = serializers.ReadOnlyField()
    can_access_virtual_tour = serializers.ReadOnlyField()
    is_past_due = serializers.ReadOnlyField()
    booking_inquiry = DirectBookingInquirySerializer(read_only=True)
    
    class Meta:
        model = Visit
        fields = [
            'id', 'listing', 'listing_title', 'buyer', 'buyer_username',
            'slot', 'slot_time', 'agent_username', 'status', 
            'selected_tour_type', 'booking_intent', 'budget_range', 'move_in_date',
            'visitor_count', 'special_requests', 'fee_amount', 'currency', 'fee_paid',
            'payment_reference', 'checkin_code', 'checkin_at', 'checkin_location',
            'virtual_tour_accessed_at', 'virtual_tour_duration',
            'proof_photo', 'buyer_rating', 'buyer_feedback', 'agent_notes',
            'can_checkin', 'can_access_virtual_tour', 'is_past_due', 
            'booking_inquiry', 'created_at', 'updated_at', 'confirmed_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'buyer', 'checkin_code', 'checkin_at', 'created_at',
            'updated_at', 'confirmed_at', 'completed_at', 'virtual_tour_accessed_at'
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
    
    def validate(self, data):
        # Validate tour type compatibility with slot
        slot = data.get('slot')
        selected_tour_type = data.get('selected_tour_type', 'onsite')
        
        if slot:
            if selected_tour_type == 'virtual' and not slot.supports_virtual:
                raise serializers.ValidationError("This slot does not support virtual tours")
            elif selected_tour_type == 'onsite' and not slot.supports_onsite:
                raise serializers.ValidationError("This slot does not support onsite tours")
        
        return data

    def validate_visitor_count(self, value):
        if hasattr(self, 'initial_data') and 'slot' in self.initial_data:
            try:
                slot = VisitSlot.objects.get(id=self.initial_data['slot'])
                if value > slot.available_capacity:
                    raise serializers.ValidationError(
                        f"Visitor count exceeds available capacity ({slot.available_capacity})"
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
        
        return super().create(validated_data)


class VisitCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating visits"""
    
    class Meta:
        model = Visit
        fields = [
            'slot', 'selected_tour_type', 'booking_intent', 'budget_range', 
            'move_in_date', 'visitor_count', 'special_requests'
        ]

    def validate_slot(self, value):
        # Check if user already has a visit for this slot
        user = self.context['request'].user
        if Visit.objects.filter(buyer=user, slot=value).exists():
            raise serializers.ValidationError("You already have a visit booked for this slot")
        
        # Check slot availability
        if value.available_capacity < 1:
            raise serializers.ValidationError("This time slot is fully booked")
        
        if value.start_at <= timezone.now():
            raise serializers.ValidationError("Cannot book visits for past time slots")
        
        return value
    
    def validate(self, data):
        # Validate tour type compatibility
        slot = data.get('slot')
        selected_tour_type = data.get('selected_tour_type', 'onsite')
        
        if slot:
            if selected_tour_type == 'virtual' and not slot.supports_virtual:
                raise serializers.ValidationError("This slot does not support virtual tours")
            elif selected_tour_type == 'onsite' and not slot.supports_onsite:
                raise serializers.ValidationError("This slot does not support onsite tours")
        
        return data


class VisitCheckinSerializer(serializers.Serializer):
    """Serializer for visit check-in"""
    
    checkin_code = serializers.CharField(max_length=8)
    location = serializers.JSONField(required=False)
    proof_photo = serializers.ImageField(required=False)

    def validate_checkin_code(self, value):
        visit = self.context['visit']
        if visit.checkin_code != value.upper():
            raise serializers.ValidationError("Invalid check-in code")
        return value.upper()


class VirtualTourAccessSerializer(serializers.Serializer):
    """Serializer for virtual tour access"""
    
    duration_seconds = serializers.IntegerField(required=False, min_value=1)
class VisitFeedbackSerializer(serializers.Serializer):
    """Serializer for visit feedback"""
    
    rating = serializers.IntegerField(min_value=1, max_value=5)
    feedback = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class DirectBookingInquiryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating booking inquiries"""
    
    class Meta:
        model = DirectBookingInquiry
        fields = [
            'offered_amount', 'currency', 'proposed_terms', 'buyer_message', 'expires_at'
        ]
    
    def validate_offered_amount(self, value):
        if value and value <= 0:
            raise serializers.ValidationError("Offered amount must be positive")
        return value
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
            'slot_time': obj.visit.slot.start_at,
            'tour_type': obj.visit.selected_tour_type
        }