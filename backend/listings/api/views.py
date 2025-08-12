from rest_framework import generics, permissions
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter, SearchFilter

from listings.models import Listing
from listings.api.serializers import ListingSerializer


class ListingFilter(filters.FilterSet):
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    bedrooms = filters.NumberFilter(field_name="bedrooms")
    bathrooms = filters.NumberFilter(field_name="bathrooms")
    area = filters.CharFilter(field_name="area", lookup_expr="iexact")
    borough = filters.CharFilter(field_name="borough", lookup_expr="icontains")
    listing_type = filters.CharFilter(field_name="listing_type", lookup_expr="iexact")
    property_status = filters.CharFilter(field_name="property_status", lookup_expr="iexact")
    furnished = filters.BooleanFilter(field_name="furnished")

    class Meta:
        model = Listing
        fields = ["area", "borough", "listing_type", "property_status", "furnished"]


class ListingList(generics.ListAPIView):
    queryset = (
        Listing.objects
        .all()
        .order_by("-date_posted")
        .select_related("seller", "seller__profile")
    )
    serializer_class = ListingSerializer
    filter_backends = [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ListingFilter
    search_fields = ["title", "description", "borough", "area"]
    ordering_fields = ["price", "date_posted", "updated_at"]


class ListingCreate(generics.CreateAPIView):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)


class ListingDetail(generics.RetrieveAPIView):
    queryset = Listing.objects.all().select_related("seller", "seller__profile")
    serializer_class = ListingSerializer


class ListingDelete(generics.DestroyAPIView):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated]
    # (Optionally enforce owner-only delete later)


class ListingUpdate(generics.UpdateAPIView):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticated]
    # (Optionally enforce owner-only )

        
        
        
    
