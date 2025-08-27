from django.urls import path
from . import views

urlpatterns = [
    path("", views.ListingList.as_view(), name="listing-list"),
    path("create/", views.ListingCreate.as_view(), name="listing-create"),
    path("<int:pk>/", views.ListingDetail.as_view(), name="listing-detail"),
    path("<int:pk>/update/", views.ListingUpdate.as_view(), name="listing-update"),
    path("<int:pk>/delete/", views.ListingDelete.as_view(), name="listing-delete"),
    
    # Tours integration
    path("<int:listing_id>/tours/", include("tours.api.urls")),
    
    # Visits integration
    path("<int:listing_id>/available-slots/", "visits.api.views.listing_available_slots", name="listing-available-slots"),
    
    # Verification integration
    path("<int:listing_id>/verify/", "verification.api.views.ListingVerifyView.as_view()", name="listing-verify"),
    path("<int:listing_id>/verification-status/", "verification.api.views.listing_verification_status", name="listing-verification-status"),
]