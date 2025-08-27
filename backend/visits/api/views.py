from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
import random
import string

from listings.models import Listing
from ..models import VisitSlot, Visit, VisitReminderTask, DirectBookingInquiry
from .serializers import (
    VisitSlotSerializer, VisitSerializer, VisitCreateSerializer,
    VisitCheckinSerializer, VirtualTourAccessSerializer, VisitFeedbackSerializer,
    DirectBookingInquirySerializer, DirectBookingInquiryCreateSerializer,
    VisitReminderTaskSerializer
)


class IsAgentOrStaff(permissions.BasePermission):
    """Allow agents (listing owners) and staff"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        if hasattr(obj, 'listing'):
            return obj.listing.seller == request.user
        elif hasattr(obj, 'agent'):
            return obj.agent == request.user
        elif hasattr(obj, 'slot'):
            return obj.slot.agent == request.user
        
        return False


class IsVisitParticipant(permissions.BasePermission):
    """Allow visit participants (buyer, agent) and staff"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return (
            obj.buyer == request.user or 
            obj.slot.agent == request.user
        )


class VisitSlotListCreateView(generics.ListCreateAPIView):
    """
    GET /api/visits/slots/ - List available visit slots
    POST /api/visits/slots/ - Create visit slot (agents only)
    """
    serializer_class = VisitSlotSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['listing', 'agent', 'tour_type', 'is_active']
    search_fields = ['listing__title', 'meeting_location', 'notes']
    ordering_fields = ['start_at', 'created_at', 'fee_amount']
    ordering = ['start_at']
    
    def get_queryset(self):
        queryset = VisitSlot.objects.select_related(
            'listing', 'agent'
        ).prefetch_related('visits')
        
        # Filter to future slots by default
        if not self.request.query_params.get('include_past'):
            queryset = queryset.filter(start_at__gt=timezone.now())
        
        # Filter by user role
        if not self.request.user.is_staff:
            if self.request.method == 'GET':
                # Users can see all active slots
                queryset = queryset.filter(is_active=True)
            else:
                # Only agents can create slots for their listings
                queryset = queryset.filter(agent=self.request.user)
        
        return queryset


class VisitSlotDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/visits/slots/{id}/
    """
    serializer_class = VisitSlotSerializer
    permission_classes = [IsAgentOrStaff]
    
    def get_queryset(self):
        return VisitSlot.objects.select_related('listing', 'agent')


class VisitListCreateView(generics.ListCreateAPIView):
    """
    GET /api/visits/ - List visits
    POST /api/visits/ - Request visit
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'listing', 'selected_tour_type']
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
            'listing', 'buyer', 'slot', 'slot__agent'
        )
        
        if user.is_staff:
            return queryset
        else:
            # Users see visits they're involved in
            return queryset.filter(
                Q(buyer=user) | Q(slot__agent=user)
            )


class VisitDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/visits/{id}/
    """
    serializer_class = VisitSerializer
    permission_classes = [IsVisitParticipant]
    
    def get_queryset(self):
        return Visit.objects.select_related(
            'listing', 'buyer', 'slot', 'slot__agent'
        )


class MyVisitsListView(generics.ListAPIView):
    """
    GET /api/visits/my-visits/
    List current user's visits
    """
    serializer_class = VisitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'selected_tour_type']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Visit.objects.filter(
            buyer=self.request.user
        ).select_related('listing', 'slot', 'slot__agent')


class AgentVisitsListView(generics.ListAPIView):
    """
    GET /api/visits/agent-visits/
    List visits for agent's properties
    """
    serializer_class = VisitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'selected_tour_type', 'listing']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return Visit.objects.filter(
            slot__agent=self.request.user
        ).select_related('listing', 'buyer', 'slot')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def confirm_visit(request, pk):
    """
    POST /api/visits/{id}/confirm/
    Confirm a visit request (agent only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if not request.user.is_staff and visit.slot.agent != request.user:
        return Response({'detail': 'Only the agent can confirm visits'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'requested':
        return Response({'detail': 'Visit is not in requested status'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Generate check-in code
    checkin_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    visit.status = 'confirmed'
    visit.checkin_code = checkin_code
    visit.confirmed_at = timezone.now()
    visit.save(update_fields=['status', 'checkin_code', 'confirmed_at', 'updated_at'])
    
    return Response({
        'status': 'confirmed',
        'checkin_code': checkin_code,
        'message': 'Visit confirmed successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_visit(request, pk):
    """
    POST /api/visits/{id}/cancel/
    Cancel a visit
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if not request.user.is_staff and visit.buyer != request.user and visit.slot.agent != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if visit.status in ['completed', 'cancelled']:
        return Response({'detail': 'Visit cannot be cancelled'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'cancelled'
    visit.save(update_fields=['status', 'updated_at'])
    
    return Response({
        'status': 'cancelled',
        'message': 'Visit cancelled successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def checkin_visit(request, pk):
    """
    POST /api/visits/{id}/checkin/
    Check in to a visit
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Only the visitor can check in'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if not visit.can_checkin:
        return Response({'detail': 'Check-in not available for this visit'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    serializer = VisitCheckinSerializer(data=request.data, context={'visit': visit})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Update visit
    visit.status = 'checked_in'
    visit.checkin_at = timezone.now()
    visit.checkin_location = serializer.validated_data.get('location')
    
    if 'proof_photo' in request.FILES:
        visit.proof_photo = request.FILES['proof_photo']
    
    visit.save(update_fields=[
        'status', 'checkin_at', 'checkin_location', 'proof_photo', 'updated_at'
    ])
    
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
    Mark visit as completed (agent only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if not request.user.is_staff and visit.slot.agent != request.user:
        return Response({'detail': 'Only the agent can complete visits'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'checked_in':
        return Response({'detail': 'Visit must be checked in before completion'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    visit.status = 'completed'
    visit.completed_at = timezone.now()
    visit.save(update_fields=['status', 'completed_at', 'updated_at'])
    
    return Response({
        'status': 'completed',
        'completed_at': visit.completed_at,
        'message': 'Visit completed successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_feedback(request, pk):
    """
    POST /api/visits/{id}/feedback/
    Submit visit feedback (buyer only)
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Only the visitor can submit feedback'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'completed':
        return Response({'detail': 'Visit must be completed before feedback'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    serializer = VisitFeedbackSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    visit.buyer_rating = serializer.validated_data['rating']
    visit.buyer_feedback = serializer.validated_data.get('feedback', '')
    visit.save(update_fields=['buyer_rating', 'buyer_feedback', 'updated_at'])
    
    return Response({
        'status': 'feedback_submitted',
        'rating': visit.buyer_rating,
        'message': 'Feedback submitted successfully'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def access_virtual_tour(request, pk):
    """
    POST /api/visits/{id}/virtual-tour/
    Access virtual tour for visit
    """
    visit = get_object_or_404(Visit, id=pk)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Only the visitor can access virtual tour'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if not visit.can_access_virtual_tour:
        return Response({'detail': 'Virtual tour access not available'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    serializer = VirtualTourAccessSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Update access time
    visit.virtual_tour_accessed_at = timezone.now()
    
    duration = serializer.validated_data.get('duration_seconds')
    if duration:
        visit.virtual_tour_duration = duration
    
    visit.save(update_fields=['virtual_tour_accessed_at', 'virtual_tour_duration', 'updated_at'])
    
    return Response({
        'status': 'access_granted',
        'accessed_at': visit.virtual_tour_accessed_at,
        'tour_url': visit.slot.virtual_tour_url,
        'message': 'Virtual tour access granted'
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def listing_available_slots(request, listing_id):
    """
    GET /api/listings/{id}/available-slots/
    Get available visit slots for a listing
    """
    listing = get_object_or_404(Listing, id=listing_id)
    
    # Get future slots with availability
    slots = VisitSlot.objects.filter(
        listing=listing,
        is_active=True,
        start_at__gt=timezone.now()
    ).exclude(
        visits__status__in=['confirmed', 'checked_in']
    ).select_related('agent').order_by('start_at')
    
    # Filter to slots with available capacity
    available_slots = [slot for slot in slots if slot.available_capacity > 0]
    
    serializer = VisitSlotSerializer(available_slots, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_upcoming_visits(request):
    """
    GET /api/visits/my-upcoming-visits/
    Get user's upcoming visits
    """
    upcoming_visits = Visit.objects.filter(
        buyer=request.user,
        status__in=['requested', 'confirmed', 'checked_in'],
        slot__start_at__gt=timezone.now()
    ).select_related('listing', 'slot', 'slot__agent').order_by('slot__start_at')
    
    serializer = VisitSerializer(upcoming_visits, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_booking_inquiry(request, visit_id):
    """
    POST /api/visits/{id}/booking-inquiry/
    Create direct booking inquiry from visit
    """
    visit = get_object_or_404(Visit, id=visit_id)
    
    # Check permissions
    if visit.buyer != request.user:
        return Response({'detail': 'Only the visitor can create booking inquiries'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if visit.status != 'completed':
        return Response({'detail': 'Visit must be completed before creating booking inquiry'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Check if inquiry already exists
    if hasattr(visit, 'booking_inquiry'):
        return Response({'detail': 'Booking inquiry already exists for this visit'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    serializer = DirectBookingInquiryCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    inquiry = serializer.save(visit=visit)
    
    return Response({
        'status': 'created',
        'inquiry_id': inquiry.id,
        'message': 'Booking inquiry created successfully'
    }, status=status.HTTP_201_CREATED)


class BookingInquiryListView(generics.ListAPIView):
    """
    GET /api/visits/booking-inquiries/
    List booking inquiries for user
    """
    serializer_class = DirectBookingInquirySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_staff:
            return DirectBookingInquiry.objects.select_related(
                'visit', 'visit__listing', 'visit__buyer'
            )
        else:
            # Users see inquiries they're involved in
            return DirectBookingInquiry.objects.filter(
                Q(visit__buyer=user) | Q(visit__slot__agent=user)
            ).select_related('visit', 'visit__listing', 'visit__buyer')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def respond_to_inquiry(request, pk):
    """
    POST /api/visits/booking-inquiries/{id}/respond/
    Respond to booking inquiry (agent only)
    """
    inquiry = get_object_or_404(DirectBookingInquiry, id=pk)
    
    # Check permissions
    if not request.user.is_staff and inquiry.visit.slot.agent != request.user:
        return Response({'detail': 'Only the agent can respond to inquiries'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    if inquiry.status != 'pending':
        return Response({'detail': 'Inquiry has already been responded to'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    response_text = request.data.get('response', '')
    new_status = request.data.get('status', 'responded')  # responded, accepted, declined
    
    if not response_text:
        return Response({'detail': 'Response text is required'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    inquiry.agent_response = response_text
    inquiry.status = new_status
    inquiry.responded_at = timezone.now()
    inquiry.save(update_fields=['agent_response', 'status', 'responded_at', 'updated_at'])
    
    return Response({
        'status': new_status,
        'message': 'Response submitted successfully',
        'responded_at': inquiry.responded_at
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def visit_analytics(request):
    """
    GET /api/visits/analytics/
    Get visit analytics for user or global (staff)
    """
    user = request.user
    
    if user.is_staff:
        # Global analytics
        from django.db.models import Avg
        
        analytics = Visit.objects.aggregate(
            total_visits=Count('id'),
            confirmed_visits=Count('id', filter=Q(status='confirmed')),
            completed_visits=Count('id', filter=Q(status='completed')),
            cancelled_visits=Count('id', filter=Q(status='cancelled')),
            avg_rating=Avg('buyer_rating', filter=Q(buyer_rating__isnull=False))
        )
        
        # Visit type distribution
        tour_type_distribution = list(
            Visit.objects.values('selected_tour_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        analytics['tour_type_distribution'] = tour_type_distribution
        
    else:
        # User analytics
        user_visits = Visit.objects.filter(
            Q(buyer=user) | Q(slot__agent=user)
        )
        
        analytics = user_visits.aggregate(
            total_visits=Count('id'),
            as_buyer=Count('id', filter=Q(buyer=user)),
            as_agent=Count('id', filter=Q(slot__agent=user)),
            completed_visits=Count('id', filter=Q(status='completed'))
        )
    
    return Response(analytics)