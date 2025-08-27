from django.urls import path
from . import views

urlpatterns = [
    # Reservations
    path('', views.ReservationListCreateView.as_view(), name='reservation-list'),
    path('<uuid:pk>/', views.ReservationDetailView.as_view(), name='reservation-detail'),
    path('<uuid:pk>/confirm/', views.confirm_reservation, name='reservation-confirm'),
    path('<uuid:pk>/complete/', views.complete_reservation, name='reservation-complete'),
    path('<uuid:pk>/cancel/', views.cancel_reservation, name='reservation-cancel'),
    
    # Disputes
    path('<uuid:reservation_id>/disputes/', views.DisputeCaseListCreateView.as_view(), name='dispute-list'),
    path('disputes/<uuid:pk>/', views.DisputeCaseDetailView.as_view(), name='dispute-detail'),
    path('disputes/<uuid:pk>/resolve/', views.resolve_dispute, name='dispute-resolve'),
    
    # Policies and analytics
    path('policies/', views.ReservationPolicyListView.as_view(), name='reservation-policy-list'),
    path('analytics/', views.reservation_analytics, name='reservation-analytics'),
]