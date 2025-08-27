from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from ..models import VisitSlot, Visit
from .serializers import (
    VisitSlotSerializer, VisitSerializer, VisitCreateSerializer,
    VisitCheckinSerializer, VisitFeedbackSerializer
)


class IsAgentOrReadOnly(permissions.BasePermission):
    """Allow agents to manage their slots, others read-only"""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.agent == request.user


class IsOwnerOrAgent(permissions.BasePermission):
    """Allow visit owner or slot agent to access"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return (
            obj.buyer == request.user or 
            obj.slot.agent == request.user or
            request.user.is_staff
        )


class VisitSlotListCreateView(generics.ListCreateAPIView):
    """
    GET /api/visits/slots/ - List available slots
    POST /api/visits/slots/ - Create new slot (agents only)
    """
    serializer_class = VisitSlotSerializer
    permission_classes = [IsAgentOrReadOnly]
    filterset_fields = ['listing', 'agent', 'is_active']
    search_fields = ['listing__title', 'notes']
    ordering_fields = ['start_at', 'created_at']
    ordering = ['start_at']
    
    def get_queryset(self):
        queryset = VisitSlot.objects.select_related('listing', 'agent')
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(start_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_at__lte=end_date)
        
        # Only show active slots for non-agents
        if not self.request.user.is_authenticated or self.request.method == 'GET':
            queryset = queryset.filter(is_active=True, start_at__gt=timezone.now())
        
        return queryset


class VisitSlotDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/visits/slots/{id}/
    """
    serializer_class = VisitSlotSerializer
    permission_classes = [IsAgentOrReadOnly]
    
    def get_queryset(self):
        return VisitSlot.objects.select_related('listing', 'agent')


class VisitListCreateView(generics.ListCreateAPIView):
    """
    GET /api/visits/ - List user's visits
    POST /api/visits/ - Request new visit
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'listing', 'slot']
    search_fields = ['listing__title', 'special_requests']
    ordering_fields = ['created_at', 'slot__start_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return VisitCreateSerializer
        return VisitSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = Visit.objects.select_related(
            'buyer', 'listing', 'slot', 'slot__agent'
        )
        
        # Users see their own visits, agents see visits for their slots
        if user.is_staff:
            return queryset
        else:
            return queryset.filter(
                Q(buyer=user) | Q(slot__agent=user)
            )
    
    def perform_create(self, serializer):
        serializer.save(buyer=self.request.user)


class VisitDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/visits/{id}/
    """
    serializer_class = VisitSerializer
    permission_classes = [IsOwnerOrAgent]
    
    def get_queryset(self):
        return Visit.objects.select_related(
            'buyer', 'listing', 'slot', 'slot__agent'
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def confirm_visit(request, pk):
    """
    POST /api/visits/{id}/confirm/
    Confirm a visit request (agents only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.slot.agent != request.user and not request.user.is_staff:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'requested':
        return Response({'detail': 'Visit is not in requested status'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check slot capacity
    if visit.slot.available_capacity < visit.visitor_count:
        return Response({'detail': 'Not enough capacity in slot'}, status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'confirmed'
    visit.confirmed_at = timezone.now()
    visit.save()
    
    return Response({
        'status': 'confirmed',
        'checkin_code': visit.checkin_code,
        'message': 'Visit confirmed successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_visit(request, pk):
    """
    POST /api/visits/{id}/cancel/
    Cancel a visit (buyer or agent)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user and visit.slot.agent != request.user and not request.user.is_staff:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status in ['completed', 'cancelled']:
        return Response({'detail': 'Cannot cancel completed or already cancelled visit'}, status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'cancelled'
    visit.save()
    
    return Response({
        'status': 'cancelled',
        'message': 'Visit cancelled successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def checkin_visit(request, pk):
    """
    POST /api/visits/{id}/checkin/
    Check in to a visit using code
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if not visit.can_checkin:
        return Response({'detail': 'Check-in not available for this visit'}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = VisitCheckinSerializer(data=request.data, context={'visit': visit})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Update visit
    visit.status = 'checked_in'
    visit.checkin_at = timezone.now()
    visit.checkin_location = serializer.validated_data.get('location', {})
    
    if 'proof_photo' in request.FILES:
        visit.proof_photo = request.FILES['proof_photo']
    
    visit.save()
    
    return Response({
        'status': 'checked_in',
        'checkin_at': visit.checkin_at,
        'message': 'Successfully checked in to visit'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_visit(request, pk):
    """
    POST /api/visits/{id}/complete/
    Mark visit as completed (agents only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.slot.agent != request.user and not request.user.is_staff:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'checked_in':
        return Response({'detail': 'Visit must be checked in to complete'}, status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'completed'
    visit.completed_at = timezone.now()
    visit.save()
    
    return Response({
        'status': 'completed',
        'completed_at': visit.completed_at,
        'message': 'Visit marked as completed'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_feedback(request, pk):
    """
    POST /api/visits/{id}/feedback/
    Submit visit feedback (buyers only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'completed':
        return Response({'detail': 'Can only provide feedback for completed visits'}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = VisitFeedbackSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    visit.buyer_rating = serializer.validated_data['rating']
    visit.buyer_feedback = serializer.validated_data.get('feedback', '')
    visit.save()
    
    return Response({
        'message': 'Feedback submitted successfully',
        'rating': visit.buyer_rating,
        'feedback': visit.buyer_feedback
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_no_show(request, pk):
    """
    POST /api/visits/{id}/no-show/
    Mark visit as no-show (agents only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.slot.agent != request.user and not request.user.is_staff:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'confirmed':
        return Response({'detail': 'Can only mark confirmed visits as no-show'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if visit time has passed
    if not visit.is_past_due:
        return Response({'detail': 'Cannot mark as no-show before visit time has passed'}, status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'no_show'
    visit.save()
    
    return Response({
        'status': 'no_show',
        'message': 'Visit marked as no-show'
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_upcoming_visits(request):
    """
    GET /api/visits/upcoming/
    Get user's upcoming visits
    """
    user = request.user
    now = timezone.now()
    
    upcoming_visits = Visit.objects.filter(
        buyer=user,
        status__in=['confirmed', 'checked_in'],
        slot__start_at__gt=now
    ).select_related('listing', 'slot', 'slot__agent').order_by('slot__start_at')
    
    serializer = VisitSerializer(upcoming_visits, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def available_slots_for_listing(request, listing_id):
    """
    GET /api/listings/{id}/available-slots/
    Get available visit slots for a specific listing
    """
    now = timezone.now()
    
    slots = VisitSlot.objects.filter(
        listing_id=listing_id,
        is_active=True,
        start_at__gt=now
    ).select_related('listing', 'agent').order_by('start_at')
    
    # Filter out full slots
    available_slots = [slot for slot in slots if slot.available_capacity > 0]
    
    serializer = VisitSlotSerializer(available_slots, many=True)
    return Response(serializer.data)