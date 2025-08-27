from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q

from ..models import TourAsset, TourAccessLog, TourTemplate
from .serializers import (
    TourAssetSerializer, TourAssetCreateSerializer, TourAccessLogSerializer,
    TourTemplateSerializer, TourAccessRequestSerializer, TourSummarySerializer
)


class IsOwnerOrStaffOrReadOnly(permissions.BasePermission):
    """Allow listing owners and staff to manage tours, others read-only"""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            request.user.is_staff or 
            obj.listing.seller == request.user
        )


class TourAssetListCreateView(generics.ListCreateAPIView):
    """
    GET /api/tours/ - List tour assets
    POST /api/tours/ - Create tour asset
    """
    permission_classes = [IsOwnerOrStaffOrReadOnly]
    filterset_fields = ['listing', 'kind', 'provider', 'is_gated', 'is_active']
    search_fields = ['title', 'description', 'listing__title']
    ordering_fields = ['created_at', 'access_count', 'title']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TourAssetCreateSerializer
        return TourAssetSerializer
    
    def get_queryset(self):
        queryset = TourAsset.objects.select_related(
            'listing', 'created_by'
        )
        
        # Filter by user's listings if not staff
        if not self.request.user.is_staff:
            if self.request.user.is_authenticated:
                # Show user's own tours and public tours
                queryset = queryset.filter(
                    Q(listing__seller=self.request.user) |
                    Q(is_active=True)
                )
            else:
                # Anonymous users see only active tours
                queryset = queryset.filter(is_active=True)
        
        return queryset


class TourAssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/tours/{id}/
    """
    serializer_class = TourAssetSerializer
    permission_classes = [IsOwnerOrStaffOrReadOnly]
    
    def get_queryset(self):
        return TourAsset.objects.select_related('listing', 'created_by')


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def request_tour_access(request, pk):
    """
    POST /api/tours/{id}/access/
    Request access to a tour (handles gating)
    """
    tour = get_object_or_404(TourAsset, id=pk, is_active=True)
    
    # Check access requirements
    allowed, reason = tour.check_access_requirements(request.user)
    
    if not allowed:
        return Response({
            'access_granted': False,
            'reason': reason,
            'requirements': tour.access_requirements
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Validate request data
    serializer = TourAccessRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Log access
    access_data = serializer.validated_data
    TourAccessLog.objects.create(
        tour_asset=tour,
        user=request.user if request.user.is_authenticated else None,
        session_id=request.session.session_key or '',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        access_method=access_data.get('access_method', 'direct'),
        referrer_url=access_data.get('referrer_url', ''),
        device_type=access_data.get('device_type', ''),
        browser=access_data.get('browser', '')
    )
    
    # Return access details
    return Response({
        'access_granted': True,
        'tour_url': tour.url,
        'embed_url': tour.get_embed_url() if tour.is_embeddable else None,
        'thumbnail_url': tour.thumbnail_url,
        'duration_seconds': tour.duration_seconds,
        'access_token': None  # Could implement JWT tokens for additional security
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def listing_tours_summary(request, listing_id):
    """
    GET /api/listings/{id}/tours/
    Get tour summary for a listing
    """
    from listings.models import Listing
    listing = get_object_or_404(Listing, id=listing_id)
    
    # Get tour statistics
    tours = TourAsset.objects.filter(listing=listing, is_active=True)
    
    # Check access for each tour
    accessible_tours = []
    for tour in tours:
        if not tour.is_gated:
            accessible_tours.append(tour)
        elif request.user.is_authenticated:
            allowed, _ = tour.check_access_requirements(request.user)
            if allowed:
                accessible_tours.append(tour)
    
    # Calculate summary
    summary_data = {
        'total_tours': tours.count(),
        'has_3d_tours': tours.filter(kind='3d').exists(),
        'has_video_tours': tours.filter(kind='video').exists(),
        'has_360_photos': tours.filter(kind='360').exists(),
        'gated_count': tours.filter(is_gated=True).count(),
        'public_tours': accessible_tours
    }
    
    serializer = TourSummarySerializer(summary_data)
    return Response(serializer.data)


class TourTemplateListView(generics.ListAPIView):
    """
    GET /api/tours/templates/
    List available tour templates
    """
    serializer_class = TourTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TourTemplate.objects.filter(is_active=True)
    filterset_fields = ['provider', 'kind']


class TourAccessLogListView(generics.ListAPIView):
    """
    GET /api/tours/{id}/analytics/
    Get access logs for a tour (owner/staff only)
    """
    serializer_class = TourAccessLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['access_method', 'device_type']
    ordering_fields = ['created_at', 'duration_seconds']
    ordering = ['-created_at']
    
    def get_queryset(self):
        tour_id = self.kwargs['tour_id']
        tour = get_object_or_404(TourAsset, id=tour_id)
        
        # Check permissions
        if not self.request.user.is_staff and tour.listing.seller != self.request.user:
            return TourAccessLog.objects.none()
        
        return TourAccessLog.objects.filter(tour_asset=tour).select_related(
            'user', 'tour_asset'
        )


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def tour_providers(request):
    """
    GET /api/tours/providers/
    Get list of supported tour providers
    """
    providers = [
        {
            'key': key,
            'name': name,
            'supports_embed': key in ['matterport', 'youtube', 'vimeo'],
            'supports_3d': key in ['matterport', 'cupix'],
            'supports_video': key in ['youtube', 'vimeo', 'custom']
        }
        for key, name in TourAsset.PROVIDER_CHOICES
    ]
    
    return Response({
        'providers': providers,
        'tour_kinds': [
            {'key': key, 'name': name}
            for key, name in TourAsset.KIND_CHOICES
        ]
    })


# Staff-only views
class StaffTourAssetListView(generics.ListAPIView):
    """
    GET /api/tours/admin/
    Staff view of all tour assets
    """
    serializer_class = TourAssetSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = TourAsset.objects.select_related('listing', 'created_by')
    filterset_fields = ['listing', 'kind', 'provider', 'is_gated', 'is_active']
    search_fields = ['title', 'description', 'listing__title', 'created_by__username']
    ordering_fields = ['created_at', 'access_count', 'title']
    ordering = ['-created_at']


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def bulk_update_tours(request):
    """
    POST /api/tours/admin/bulk-update/
    Bulk update tour assets (staff only)
    """
    tour_ids = request.data.get('tour_ids', [])
    updates = request.data.get('updates', {})
    
    if not tour_ids or not updates:
        return Response({
            'error': 'tour_ids and updates are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate updates
    allowed_fields = ['is_active', 'is_gated', 'access_requirements']
    filtered_updates = {
        k: v for k, v in updates.items() 
        if k in allowed_fields
    }
    
    if not filtered_updates:
        return Response({
            'error': 'No valid update fields provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Perform bulk update
    updated_count = TourAsset.objects.filter(
        id__in=tour_ids
    ).update(**filtered_updates)
    
    return Response({
        'updated_count': updated_count,
        'message': f'Successfully updated {updated_count} tour assets'
    })