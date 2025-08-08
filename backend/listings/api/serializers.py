from math import radians, sin, cos, acos
from rest_framework import serializers
from .models import Listing, Poi

class PoiSerializer(serializers.ModelSerializer):
    distance_km = serializers.FloatField(read_only=True)  # populated in serializer method

    class Meta:
        model = Poi
        fields = "__all__"


def spherical_distance_km(lat1, lon1, lat2, lon2):
    """
    Spherical law of cosines: accurate enough for <= few hundred km.
    Returns distance in kilometers.
    """
    R = 6371.0
    φ1, λ1, φ2, λ2 = map(radians, [lat1, lon1, lat2, lon2])
    # guard against fp rounding outside [-1, 1]
    cos_val = sin(φ1) * sin(φ2) + cos(φ1) * cos(φ2) * cos(λ2 - λ1)
    cos_val = max(-1.0, min(1.0, cos_val))
    return R * acos(cos_val)


class ListingSerializer(serializers.ModelSerializer):
    country = serializers.SerializerMethodField()
    seller_username = serializers.SerializerMethodField()
    seller_agency_name = serializers.SerializerMethodField()
    listing_pois_within_10km = serializers.SerializerMethodField()

    def get_listing_pois_within_10km(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return []

        lat, lon = obj.latitude, obj.longitude
        radius_km = 10.0

        # quick SQL prefilter using a bounding box
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * max(0.000001, cos(radians(lat))))

        pre_qs = Poi.objects.filter(
            latitude__gte=lat - lat_delta,
            latitude__lte=lat + lat_delta,
            longitude__gte=lon - lon_delta,
            longitude__lte=lon + lon_delta,
        )

        results = []
        for poi in pre_qs:
            d = spherical_distance_km(lat, lon, poi.latitude, poi.longitude)
            if d <= radius_km:
                data = PoiSerializer(poi).data
                data["distance_km"] = round(d, 3)
                results.append(data)

        # sort by distance
        results.sort(key=lambda x: x["distance_km"])
        return results

    def get_seller_agency_name(self, obj):
        # Safe getattr chain; returns None if missing
        seller = getattr(obj, "seller", None)
        profile = getattr(seller, "profile", None) if seller else None
        return getattr(profile, "agency_name", None)

    def get_seller_username(self, obj):
        seller = getattr(obj, "seller", None)
        return getattr(seller, "username", None)

    def get_country(self, obj):
        return "England"

    class Meta:
        model = Listing
        fields = "__all__"
