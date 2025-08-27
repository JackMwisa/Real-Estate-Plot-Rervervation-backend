from django.urls import path
from . import views

urlpatterns = [
    # Tour assets
    path('', views.TourAssetListCreateView.as_view(), name='tour-asset-list'),
    path('<uuid:pk>/', views.TourAssetDetailView.as_view(), name='tour-asset-detail'),
    path('<uuid:pk>/access/', views.request_tour_access, name='tour-request-access'),
    path('<uuid:tour_id>/analytics/', views.TourAccessLogListView.as_view(), name='tour-analytics'),
    
    # Templates and providers
    path('templates/', views.TourTemplateListView.as_view(), name='tour-template-list'),
    path('providers/', views.tour_providers, name='tour-providers'),
    
    # Staff endpoints
    path('admin/', views.StaffTourAssetListView.as_view(), name='staff-tour-list'),
    path('admin/bulk-update/', views.bulk_update_tours, name='bulk-update-tours'),
]