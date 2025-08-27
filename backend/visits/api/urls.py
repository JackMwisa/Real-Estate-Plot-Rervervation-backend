from django.urls import path
from . import views

urlpatterns = [
    # Visit slots
    path("slots/", views.VisitSlotListCreateView.as_view(), name="visit-slot-list"),
    path("slots/<uuid:pk>/", views.VisitSlotDetailView.as_view(), name="visit-slot-detail"),
    
    # Visits
    path("", views.VisitListCreateView.as_view(), name="visit-list"),
    path("<uuid:pk>/", views.VisitDetailView.as_view(), name="visit-detail"),
    path("<uuid:pk>/confirm/", views.confirm_visit, name="visit-confirm"),
    path("<uuid:pk>/cancel/", views.cancel_visit, name="visit-cancel"),
    path("<uuid:pk>/checkin/", views.checkin_visit, name="visit-checkin"),
    path("<uuid:pk>/complete/", views.complete_visit, name="visit-complete"),
    path("<uuid:pk>/feedback/", views.submit_feedback, name="visit-feedback"),
    path("<uuid:pk>/virtual-tour/", views.access_virtual_tour, name="visit-virtual-tour"),
    
    # User-specific endpoints
    path("my-visits/", views.MyVisitsListView.as_view(), name="my-visits"),
    path("my-upcoming-visits/", views.my_upcoming_visits, name="my-upcoming-visits"),
    path("agent-visits/", views.AgentVisitsListView.as_view(), name="agent-visits"),
    
    # Direct booking inquiries
    path("<uuid:visit_id>/booking-inquiry/", views.create_booking_inquiry, name="create-booking-inquiry"),
    path("booking-inquiries/", views.BookingInquiryListView.as_view(), name="booking-inquiry-list"),
    path("booking-inquiries/<uuid:pk>/respond/", views.respond_to_inquiry, name="respond-to-inquiry"),
    
    # Analytics
    path("analytics/", views.visit_analytics, name="visit-analytics"),
]