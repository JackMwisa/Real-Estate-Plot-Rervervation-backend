from django.urls import path
from . import views

urlpatterns = [
    # Public package endpoints
    path('packages/', views.AdPackageListView.as_view(), name='ad-package-list'),
    path('packages/<uuid:pk>/', views.AdPackageDetailView.as_view(), name='ad-package-detail'),
    
    # Campaign management
    path('campaigns/', views.AdCampaignListCreateView.as_view(), name='ad-campaign-list'),
    path('campaigns/<uuid:pk>/', views.AdCampaignDetailView.as_view(), name='ad-campaign-detail'),
    path('campaigns/<uuid:pk>/metrics/', views.AdCampaignMetricsView.as_view(), name='ad-campaign-metrics'),
    path('campaigns/<uuid:pk>/pause/', views.pause_campaign, name='ad-campaign-pause'),
    path('campaigns/<uuid:pk>/resume/', views.resume_campaign, name='ad-campaign-resume'),
    
    # Ad tracking
    path('track/', views.track_ad_event, name='ad-track-event'),
    
    # Staff/admin endpoints
    path('admin/campaigns/', views.StaffAdCampaignListView.as_view(), name='staff-ad-campaign-list'),
    path('admin/campaigns/<uuid:pk>/approve/', views.approve_campaign, name='staff-approve-campaign'),
    path('admin/campaigns/<uuid:pk>/reject/', views.reject_campaign, name='staff-reject-campaign'),
]