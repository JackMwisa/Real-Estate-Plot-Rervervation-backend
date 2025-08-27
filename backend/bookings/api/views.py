from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction

from ..models import Reservation, DisputeCase, ReservationPolicy
from .serializers import (
    ReservationSerializer, ReservationCreateSerializer, DisputeCaseSerializer,
    DisputeCaseCreateSerializer, DisputeResolutionSerializer, ReservationCancelSerializer,
    ReservationPolicySerializer
)


class IsInvolvedInReservation(permissions.BasePermission):
    """Allow users involved in reservation (buyer or listing owner) plus staff"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return (
            obj.buyer == request.user or 
            obj.listing.seller == request.user
        )


class ReservationListCreateView(generics.ListCreateAPIView):
    """
    GET /api/bookings/ - List user's reservations
    POST /api/bookings/ - Create new reservation
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['escrow_state', 'reservation_type', 'listing']
    search_fields = ['listing__title', 'escrow_reference']
    ordering_fields = ['created_at', 'start_at', 'amount']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReservationCreateSerializer
        return ReservationSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = Reservation.objects.select_related(
            'listing', 'buyer', 'visit', 'cancelled_by'
        )
        
        if user.is_staff:
            return queryset
        else:
            # Users see reservations they're involved in
            return queryset.filter(
                models.Q(buyer=user) | models.Q(listing__seller=user)
            )


class ReservationDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/bookings/{id}/
    """
    serializer_class = ReservationSerializer
    permission_classes = [IsInvolvedInReservation]
    
    def get_queryset(self):
        return Reservation.objects.select_related(
            'listing', 'buyer', 'visit', 'cancelled_by'
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def confirm_reservation(request, pk):
    """
    POST /api/bookings/{id}/confirm/
    Confirm a paid reservation (listing owner only)
    """
    reservation = get_object_or_404(Reservation, id=pk)
    
    # Check permissions
    if not request.user.is_staff and reservation.listing.seller != request.user:
        return Response({'detail': 'Only the listing owner can confirm reservations'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if reservation.escrow_state != 'paid':
        return Response({'detail': 'Reservation must be paid before confirmation'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    reservation.escrow_state = 'confirmed'
    reservation.confirmed_at = timezone.now()
    reservation.save(update_fields=['escrow_state', 'confirmed_at', 'updated_at'])
    
    return Response({
        'status': 'confirmed',
        'message': 'Reservation confirmed successfully',
        'confirmed_at': reservation.confirmed_at
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_reservation(request, pk):
    """
    POST /api/bookings/{id}/complete/
    Mark reservation as completed (listing owner only)
    """
    reservation = get_object_or_404(Reservation, id=pk)
    
    # Check permissions
    if not request.user.is_staff and reservation.listing.seller != request.user:
        return Response({'detail': 'Only the listing owner can complete reservations'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if reservation.escrow_state != 'confirmed':
        return Response({'detail': 'Reservation must be confirmed before completion'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    reservation.escrow_state = 'completed'
    reservation.completed_at = timezone.now()
    reservation.save(update_fields=['escrow_state', 'completed_at', 'updated_at'])
    
    return Response({
        'status': 'completed',
        'message': 'Reservation completed successfully',
        'completed_at': reservation.completed_at
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_reservation(request, pk):
    """
    POST /api/bookings/{id}/cancel/
    Cancel a reservation
    """
    reservation = get_object_or_404(Reservation, id=pk)
    
    # Check permissions
    if not request.user.is_staff and reservation.buyer != request.user and reservation.listing.seller != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    serializer = ReservationCancelSerializer(
        data=request.data, 
        context={'reservation': reservation}
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Calculate refund amount
    refund_amount = reservation.calculate_refund_amount()
    
    with transaction.atomic():
        reservation.escrow_state = 'cancelled'
        reservation.cancellation_reason = serializer.validated_data['reason']
        reservation.cancelled_by = request.user
        reservation.cancelled_at = timezone.now()
        reservation.save(update_fields=[
            'escrow_state', 'cancellation_reason', 'cancelled_by', 
            'cancelled_at', 'updated_at'
        ])
        
        # If there's a refund amount, mark for refund processing
        if refund_amount > 0:
            reservation.escrow_state = 'refunded'
            reservation.save(update_fields=['escrow_state', 'updated_at'])
    
    return Response({
        'status': 'cancelled',
        'message': 'Reservation cancelled successfully',
        'refund_amount': refund_amount,
        'cancelled_at': reservation.cancelled_at
    })


class DisputeCaseListCreateView(generics.ListCreateAPIView):
    """
    GET /api/bookings/{reservation_id}/disputes/ - List disputes for reservation
    POST /api/bookings/{reservation_id}/disputes/ - Create new dispute
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'dispute_type', 'priority']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return DisputeCaseCreateSerializer
        return DisputeCaseSerializer
    
    def get_queryset(self):
        reservation_id = self.kwargs['reservation_id']
        reservation = get_object_or_404(Reservation, id=reservation_id)
        
        # Check permissions
        user = self.request.user
        if not user.is_staff and reservation.buyer != user and reservation.listing.seller != user:
            return DisputeCase.objects.none()
        
        return DisputeCase.objects.filter(reservation=reservation).select_related(
            'opener', 'assigned_to', 'resolved_by'
        )
    
    def perform_create(self, serializer):
        reservation_id = self.kwargs['reservation_id']
        reservation = get_object_or_404(Reservation, id=reservation_id)
        
        # Check permissions
        user = self.request.user
        if reservation.buyer != user and reservation.listing.seller != user:
            raise permissions.PermissionDenied()
        
        # Update reservation state to disputed
        if reservation.escrow_state in ['confirmed', 'completed']:
            reservation.escrow_state = 'disputed'
            reservation.save(update_fields=['escrow_state', 'updated_at'])
        
        serializer.save(reservation=reservation)


class DisputeCaseDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/bookings/disputes/{id}/
    """
    serializer_class = DisputeCaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return DisputeCase.objects.select_related(
            'reservation', 'opener', 'assigned_to', 'resolved_by'
        )
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        
        # Check permissions
        if not user.is_staff:
            reservation = obj.reservation
            if reservation.buyer != user and reservation.listing.seller != user:
                raise permissions.PermissionDenied()
        
        return obj


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resolve_dispute(request, pk):
    """
    POST /api/bookings/disputes/{id}/resolve/
    Resolve a dispute (staff only)
    """
    if not request.user.is_staff:
        return Response({'detail': 'Only staff can resolve disputes'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    dispute = get_object_or_404(DisputeCase, id=pk)
    
    if dispute.is_resolved:
        return Response({'detail': 'Dispute is already resolved'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    serializer = DisputeResolutionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    with transaction.atomic():
        # Update dispute
        dispute.status = 'resolved'
        dispute.resolution = data['resolution']
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.refund_amount = data.get('refund_amount')
        dispute.compensation_amount = data.get('compensation_amount')
        dispute.save()
        
        # Update reservation state if specified
        new_state = data.get('new_escrow_state')
        if new_state:
            dispute.reservation.escrow_state = new_state
            dispute.reservation.save(update_fields=['escrow_state', 'updated_at'])
    
    return Response({
        'status': 'resolved',
        'message': 'Dispute resolved successfully',
        'resolution': dispute.resolution,
        'resolved_at': dispute.resolved_at
    })


class ReservationPolicyListView(generics.ListAPIView):
    """
    GET /api/bookings/policies/
    List available reservation policies
    """
    serializer_class = ReservationPolicySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ReservationPolicy.objects.filter(is_active=True)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def reservation_analytics(request):
    """
    GET /api/bookings/analytics/
    Get reservation analytics for user or staff
    """
    user = request.user
    
    if user.is_staff:
        # Staff sees global analytics
        from django.db.models import Count, Sum, Avg
        
        analytics = Reservation.objects.aggregate(
            total_reservations=Count('id'),
            total_value=Sum('amount'),
            avg_reservation_value=Avg('amount'),
            active_reservations=Count('id', filter=models.Q(escrow_state__in=['paid', 'confirmed'])),
            completed_reservations=Count('id', filter=models.Q(escrow_state='completed')),
            disputed_reservations=Count('id', filter=models.Q(escrow_state='disputed'))
        )
        
        # State distribution
        state_distribution = list(
            Reservation.objects.values('escrow_state')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        analytics['state_distribution'] = state_distribution
        
    else:
        # Users see their own analytics
        user_reservations = Reservation.objects.filter(
            models.Q(buyer=user) | models.Q(listing__seller=user)
        )
        
        from django.db.models import Count, Sum
        
        analytics = user_reservations.aggregate(
            total_reservations=Count('id'),
            total_value=Sum('amount'),
            as_buyer=Count('id', filter=models.Q(buyer=user)),
            as_seller=Count('id', filter=models.Q(listing__seller=user))
        )
    
    return Response(analytics)