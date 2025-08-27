from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from ..models import Reservation, DisputeCase, ReservationPolicy

User = get_user_model()


class ReservationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationPolicy
        fields = [
            'id', 'name', 'description', 'full_refund_days', 'partial_refund_days',
            'partial_refund_percent', 'security_deposit_percent', 'security_deposit_fixed',
            'terms_and_conditions', 'requires_verification', 'is_active'
        ]
        read_only_fields = ['id']


class ReservationSerializer(serializers.ModelSerializer):
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    listing_seller = serializers.CharField(source='listing.seller.username', read_only=True)
    visit_details = serializers.SerializerMethodField()
    total_amount = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    is_pending = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    can_cancel = serializers.ReadOnlyField()
    can_dispute = serializers.ReadOnlyField()
    refund_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = Reservation
        fields = [
            'id', 'listing', 'listing_title', 'listing_seller', 'buyer', 'buyer_username',
            'visit', 'visit_details', 'reservation_type', 'start_at', 'end_at',
            'amount', 'currency', 'security_deposit', 'total_amount', 'escrow_state',
            'escrow_reference', 'policy', 'terms_accepted_at', 'cancellation_reason',
            'cancelled_by', 'cancelled_at', 'is_active', 'is_pending', 'is_completed',
            'can_cancel', 'can_dispute', 'refund_amount', 'created_at', 'updated_at',
            'confirmed_at', 'completed_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'buyer', 'escrow_reference', 'cancelled_by', 'cancelled_at',
            'created_at', 'updated_at', 'confirmed_at', 'completed_at'
        ]

    def get_visit_details(self, obj):
        if not obj.visit:
            return None
        return {
            'id': str(obj.visit.id),
            'status': obj.visit.status,
            'selected_tour_type': obj.visit.selected_tour_type,
            'slot_time': {
                'start_at': obj.visit.slot.start_at,
                'end_at': obj.visit.slot.end_at
            }
        }

    def get_refund_amount(self, obj):
        return obj.calculate_refund_amount()

    def validate(self, data):
        # Validate date range for rentals/short stays
        start_at = data.get('start_at')
        end_at = data.get('end_at')
        reservation_type = data.get('reservation_type')
        
        if reservation_type in ['rental', 'short_stay']:
            if not start_at or not end_at:
                raise serializers.ValidationError("Start and end dates are required for rentals and short stays")
            
            if start_at >= end_at:
                raise serializers.ValidationError("End date must be after start date")
            
            if start_at <= timezone.now():
                raise serializers.ValidationError("Start date must be in the future")
        
        # Validate verification requirement
        listing = data.get('listing')
        if listing:
            policy = data.get('policy', {})
            if policy.get('requires_verification', False):
                # Check if listing is verified
                from verification.models import VerificationCase
                verified_case = VerificationCase.objects.filter(
                    listing=listing,
                    case_type='listing',
                    status='verified'
                ).first()
                
                if not verified_case:
                    raise serializers.ValidationError("This listing requires verification before reservations can be made")
        
        return data


class ReservationCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating reservations"""
    
    class Meta:
        model = Reservation
        fields = [
            'listing', 'visit', 'reservation_type', 'start_at', 'end_at',
            'amount', 'currency', 'security_deposit', 'policy', 'metadata'
        ]

    def validate_listing(self, value):
        """Ensure listing is available for reservation"""
        if value.property_status != 'available':
            raise serializers.ValidationError("This listing is not available for reservation")
        return value

    def validate_visit(self, value):
        """Ensure visit belongs to the user"""
        user = self.context['request'].user
        if value and value.buyer != user:
            raise serializers.ValidationError("You can only create reservations for your own visits")
        return value

    def create(self, validated_data):
        # Set buyer to current user
        validated_data['buyer'] = self.context['request'].user
        
        # Generate escrow reference
        import uuid
        validated_data['escrow_reference'] = f"ESC-{uuid.uuid4().hex[:8].upper()}"
        
        return super().create(validated_data)


class DisputeCaseSerializer(serializers.ModelSerializer):
    opener_username = serializers.CharField(source='opener.username', read_only=True)
    reservation_details = serializers.SerializerMethodField()
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)
    is_open = serializers.ReadOnlyField()
    is_resolved = serializers.ReadOnlyField()
    
    class Meta:
        model = DisputeCase
        fields = [
            'id', 'reservation', 'reservation_details', 'dispute_type', 'opener',
            'opener_username', 'status', 'title', 'description', 'evidence_json',
            'resolution', 'resolved_by', 'resolved_by_username', 'resolved_at',
            'refund_amount', 'compensation_amount', 'priority', 'assigned_to',
            'assigned_to_username', 'is_open', 'is_resolved', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'opener', 'resolved_by', 'resolved_at', 'created_at', 'updated_at'
        ]

    def get_reservation_details(self, obj):
        return {
            'id': str(obj.reservation.id),
            'listing_title': obj.reservation.listing.title,
            'amount': str(obj.reservation.amount),
            'currency': obj.reservation.currency,
            'escrow_state': obj.reservation.escrow_state
        }


class DisputeCaseCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating dispute cases"""
    
    class Meta:
        model = DisputeCase
        fields = [
            'reservation', 'dispute_type', 'title', 'description', 
            'evidence_json', 'priority'
        ]

    def validate_reservation(self, value):
        """Ensure user can dispute this reservation"""
        user = self.context['request'].user
        
        # Check if user is involved in the reservation
        if value.buyer != user and value.listing.seller != user:
            raise serializers.ValidationError("You can only dispute reservations you're involved in")
        
        # Check if reservation can be disputed
        if not value.can_dispute:
            raise serializers.ValidationError("This reservation cannot be disputed in its current state")
        
        # Check for existing open disputes
        existing_dispute = DisputeCase.objects.filter(
            reservation=value,
            status__in=['open', 'investigating', 'awaiting_response']
        ).first()
        
        if existing_dispute:
            raise serializers.ValidationError("There is already an open dispute for this reservation")
        
        return value

    def create(self, validated_data):
        validated_data['opener'] = self.context['request'].user
        return super().create(validated_data)


class DisputeResolutionSerializer(serializers.Serializer):
    """Serializer for resolving disputes"""
    
    resolution = serializers.CharField(max_length=2000)
    refund_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False,
        min_value=Decimal('0.00')
    )
    compensation_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False,
        min_value=Decimal('0.00')
    )
    new_escrow_state = serializers.ChoiceField(
        choices=['refunded', 'released', 'completed'],
        required=False
    )

    def validate(self, data):
        refund = data.get('refund_amount', Decimal('0.00'))
        compensation = data.get('compensation_amount', Decimal('0.00'))
        
        if refund > 0 and not data.get('new_escrow_state'):
            data['new_escrow_state'] = 'refunded'
        elif compensation > 0 and not data.get('new_escrow_state'):
            data['new_escrow_state'] = 'released'
        
        return data


class ReservationCancelSerializer(serializers.Serializer):
    """Serializer for cancelling reservations"""
    
    reason = serializers.CharField(max_length=500)
    
    def validate(self, data):
        reservation = self.context['reservation']
        
        if not reservation.can_cancel:
            raise serializers.ValidationError("This reservation cannot be cancelled in its current state")
        
        return data