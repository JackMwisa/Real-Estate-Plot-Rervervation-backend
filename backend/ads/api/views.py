from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta

from ..models import AdPackage, AdCampaign, AdImpression, AdClick, AdMetricsRollup
from .serializers import (
    AdPackageSerializer, AdCampaignSerializer, AdCampaignCreateSerializer,
    AdImpressionSerializer, AdClickSerializer, AdMetricsRollupSerializer,
    CampaignMetricsSerializer, AdTrackingSerializer
)


class IsOwnerOrStaff(permissions.BasePermission):
    """Allow staff to see all campaigns, users to see only their own"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.owner == request.user


class AdPackageListView(generics.ListAPIView):
    """
    GET /api/ads/packages/
    List available ad packages (public)
    """
    serializer_class = AdPackageSerializer
    queryset = AdPackage.objects.filter(is_active=True)
    permission_classes = [permissions.AllowAny]


class AdPackageDetailView(generics.RetrieveAPIView):
    """
    GET /api/ads/packages/{id}/
    Get ad package details (public)
    """
    serializer_class = AdPackageSerializer
    queryset = AdPackage.objects.filter(is_active=True)
    permission_classes = [permissions.AllowAny]


class AdCampaignListCreateView(generics.ListCreateAPIView):
    """
    GET /api/ads/campaigns/ - List user's campaigns
    POST /api/ads/campaigns/ - Create new campaign
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'target_type', 'package']
    search_fields = ['notes']
    ordering_fields = ['created_at', 'start_at', 'budget', 'impressions', 'clicks']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdCampaignCreateSerializer
        return AdCampaignSerializer
    
    def get_queryset(self):
        queryset = AdCampaign.objects.select_related('owner', 'package')
        
        if self.request.user.is_staff:
            return queryset
        else:
            return queryset.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class AdCampaignDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/ads/campaigns/{id}/
    Campaign CRUD operations
    """
    serializer_class = AdCampaignSerializer
    permission_classes = [IsOwnerOrStaff]
    
    def get_queryset(self):
        return AdCampaign.objects.select_related('owner', 'package')


class AdCampaignMetricsView(generics.RetrieveAPIView):
    """
    GET /api/ads/campaigns/{id}/metrics/
    Get detailed campaign performance metrics
    """
    permission_classes = [IsOwnerOrStaff]
    serializer_class = CampaignMetricsSerializer
    
    def get_object(self):
        campaign_id = self.kwargs['pk']
        return get_object_or_404(AdCampaign, id=campaign_id)
    
    def retrieve(self, request, *args, **kwargs):
        campaign = self.get_object()
        
        # Check permissions
        if not request.user.is_staff and campaign.owner != request.user:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        # Get daily metrics for the last 30 days
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        daily_metrics = AdMetricsRollup.objects.filter(
            campaign=campaign,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        # Calculate totals
        totals = daily_metrics.aggregate(
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            total_conversions=Sum('conversions'),
            total_spend=Sum('spend')
        )
        
        # Calculate averages
        average_ctr = 0.0
        average_cpc = 0.0
        
        if totals['total_impressions']:
            average_ctr = (totals['total_clicks'] / totals['total_impressions']) * 100
        
        if totals['total_clicks']:
            average_cpc = totals['total_spend'] / totals['total_clicks']
        
        data = {
            'total_impressions': totals['total_impressions'] or 0,
            'total_clicks': totals['total_clicks'] or 0,
            'total_conversions': totals['total_conversions'] or 0,
            'total_spend': totals['total_spend'] or 0,
            'average_ctr': average_ctr,
            'average_cpc': average_cpc,
            'daily_metrics': AdMetricsRollupSerializer(daily_metrics, many=True).data
        }
        
        serializer = self.get_serializer(data)
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def pause_campaign(request, pk):
    """
    POST /api/ads/campaigns/{id}/pause/
    Pause an active campaign
    """
    campaign = get_object_or_404(AdCampaign, id=pk)
    
    # Check permissions
    if not request.user.is_staff and campaign.owner != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if campaign.status != 'active':
        return Response({'detail': 'Campaign is not active'}, status=status.HTTP_400_BAD_REQUEST)
    
    campaign.status = 'paused'
    campaign.save(update_fields=['status', 'updated_at'])
    
    return Response({'status': 'paused', 'message': 'Campaign paused successfully'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resume_campaign(request, pk):
    """
    POST /api/ads/campaigns/{id}/resume/
    Resume a paused campaign
    """
    campaign = get_object_or_404(AdCampaign, id=pk)
    
    # Check permissions
    if not request.user.is_staff and campaign.owner != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    if campaign.status != 'paused':
        return Response({'detail': 'Campaign is not paused'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if campaign is still within date range and budget
    now = timezone.now()
    if now > campaign.end_at:
        return Response({'detail': 'Campaign has expired'}, status=status.HTTP_400_BAD_REQUEST)
    
    if campaign.spent_amount >= campaign.budget:
        return Response({'detail': 'Campaign budget exhausted'}, status=status.HTTP_400_BAD_REQUEST)
    
    campaign.status = 'active'
    campaign.save(update_fields=['status', 'updated_at'])
    
    return Response({'status': 'active', 'message': 'Campaign resumed successfully'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def track_ad_event(request):
    """
    POST /api/ads/track/
    Track ad impressions and clicks
    """
    serializer = AdTrackingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    campaign_id = data['campaign_id']
    event_type = data['event_type']
    
    try:
        campaign = AdCampaign.objects.get(id=campaign_id)
    except AdCampaign.DoesNotExist:
        return Response({'detail': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if not campaign.can_serve_ad():
        return Response({'detail': 'Campaign cannot serve ads'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get user context
    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''
    ip_address = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    if event_type == 'impression':
        # Create impression record
        impression = AdImpression.objects.create(
            campaign=campaign,
            user=user,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            page_url=data.get('page_url', ''),
            search_query=data.get('search_query', ''),
            position=data.get('position'),
            cost=campaign.package.price if campaign.package.pricing_model == 'cpm' else 0
        )
        
        return Response({
            'status': 'recorded',
            'event_type': 'impression',
            'impression_id': impression.id
        })
    
    elif event_type == 'click':
        # Find related impression (optional)
        impression = None
        if user:
            impression = AdImpression.objects.filter(
                campaign=campaign,
                user=user,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).first()
        elif session_id:
            impression = AdImpression.objects.filter(
                campaign=campaign,
                session_id=session_id,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).first()
        
        # Create click record
        click = AdClick.objects.create(
            campaign=campaign,
            impression=impression,
            user=user,
            session_id=session_id,
            ip_address=ip_address,
            clicked_url=data.get('clicked_url', ''),
            referrer_url=data.get('referrer_url', ''),
            cost=campaign.package.price if campaign.package.pricing_model == 'cpc' else 0
        )
        
        return Response({
            'status': 'recorded',
            'event_type': 'click',
            'click_id': click.id
        })
    
    return Response({'detail': 'Invalid event type'}, status=status.HTTP_400_BAD_REQUEST)


# Staff-only views for campaign management
class StaffAdCampaignListView(generics.ListAPIView):
    """
    GET /api/ads/admin/campaigns/
    Staff view of all campaigns with filtering
    """
    serializer_class = AdCampaignSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = AdCampaign.objects.select_related('owner', 'package')
    filterset_fields = ['status', 'target_type', 'package', 'owner']
    search_fields = ['owner__username', 'owner__email', 'notes']
    ordering_fields = ['created_at', 'start_at', 'budget', 'impressions', 'clicks']
    ordering = ['-created_at']


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def approve_campaign(request, pk):
    """
    POST /api/ads/admin/campaigns/{id}/approve/
    Approve a pending campaign (staff only)
    """
    campaign = get_object_or_404(AdCampaign, id=pk)
    
    if campaign.status != 'pending':
        return Response({'detail': 'Campaign is not pending approval'}, status=status.HTTP_400_BAD_REQUEST)
    
    campaign.status = 'active'
    campaign.approved_at = timezone.now()
    campaign.approved_by = request.user
    campaign.save(update_fields=['status', 'approved_at', 'approved_by', 'updated_at'])
    
    return Response({
        'status': 'approved',
        'message': 'Campaign approved and activated',
        'approved_at': campaign.approved_at
    })


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def reject_campaign(request, pk):
    """
    POST /api/ads/admin/campaigns/{id}/reject/
    Reject a pending campaign (staff only)
    """
    campaign = get_object_or_404(AdCampaign, id=pk)
    
    if campaign.status != 'pending':
        return Response({'detail': 'Campaign is not pending approval'}, status=status.HTTP_400_BAD_REQUEST)
    
    reason = request.data.get('reason', '')
    
    campaign.status = 'cancelled'
    campaign.notes = f"Rejected: {reason}" if reason else "Rejected by staff"
    campaign.save(update_fields=['status', 'notes', 'updated_at'])
    
    return Response({
        'status': 'rejected',
        'message': 'Campaign rejected',
        'reason': reason
    })