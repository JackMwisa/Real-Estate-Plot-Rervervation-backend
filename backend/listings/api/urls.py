
from django.urls import path, include
from . import views

#  import the actual callables you reference
from visits.api.views import listing_available_slots            # was a string before
from verification.api.views import (
    ListingVerifyView,                                          # class-based view
    listing_verification_status,                                # function view
)

urlpatterns = [
    path("", views.ListingList.as_view(), name="listing-list"),
    path("create/", views.ListingCreate.as_view(), name="listing-create"),
    path("<int:pk>/", views.ListingDetail.as_view(), name="listing-detail"),
    path("<int:pk>/update/", views.ListingUpdate.as_view(), name="listing-update"),
    path("<int:pk>/delete/", views.ListingDelete.as_view(), name="listing-delete"),

    # Tours integration (already correct)
    path("<int:listing_id>/tours/", include("tours.api.urls")),

    # Visits integration — pass the callable, not a string
    path("<int:listing_id>/available-slots/", listing_available_slots,
         name="listing-available-slots"),

    # Verification integration — import & call as_view() for CBV
    path("<int:listing_id>/verify/", ListingVerifyView.as_view(), name="listing-verify"),
    path("<int:listing_id>/verification-status/", listing_verification_status,
         name="listing-verification-status"),
]
