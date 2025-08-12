from math import radians, sin, cos, acos
from rest_framework import serializers
from listings.models import Listing, Poi


class PoiSerializer(serializers.ModelSerializer):
    distance_km = serializers.FloatField(read_only=True)

    class Meta:
        model = Poi
        fields = "__all__"


def spherical_distance_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    φ1, λ1, φ2, λ2 = map(radians, [lat1, lon1, lat2, lon2])
    val = sin(φ1) * sin(φ2) + cos(φ1) * cos(φ2) * cos(λ2 - λ1)
    val = max(-1.0, min(1.0, val))
    return R * acos(val)


class ListingSerializer(serializers.ModelSerializer):
    country = serializers.SerializerMethodField()
    seller_username = serializers.SerializerMethodField()
    seller_agency_name = serializers.SerializerMethodField()
    listing_pois_within_10km = serializers.SerializerMethodField()
    image_main_url = serializers.SerializerMethodField()
    # Placeholder for Phase 1; will return real value after we add favorites app
    is_favorited = serializers.SerializerMethodField()

    def get_image_main_url(self, obj):
        req = self.context.get("request")
        if obj.image_main and hasattr(obj.image_main, "url"):
            return req.build_absolute_uri(obj.image_main.url) if req else obj.image_main.url
        return None

    def get_listing_pois_within_10km(self, obj):
        # Optional: only compute when ?include_pois=1 to reduce cost
        req = self.context.get("request")
        if req and req.query_params.get("include_pois") not in ("1", "true", "True"):
            return []

        if obj.latitude is None or obj.longitude is None:
            return []

        lat, lon, radius_km = obj.latitude, obj.longitude, 10.0
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * max(0.000001, cos(radians(lat))))

        pre_qs = Poi.objects.filter(
            latitude__gte=lat - lat_delta, latitude__lte=lat + lat_delta,
            longitude__gte=lon - lon_delta, longitude__lte=lon + lon_delta,
        )

        out = []
        for poi in pre_qs:
            d = spherical_distance_km(lat, lon, poi.latitude, poi.longitude)
            if d <= radius_km:
                row = PoiSerializer(poi).data
                row["distance_km"] = round(d, 3)
                out.append(row)
        out.sort(key=lambda r: r["distance_km"])
        return out

    def get_seller_agency_name(self, obj):
        prof = getattr(getattr(obj, "seller", None), "profile", None)
        return getattr(prof, "agency_name", None)

    def get_seller_username(self, obj):
        return getattr(getattr(obj, "seller", None), "username", None)

    def get_country(self, obj):
        # Your market is UG; change if you enrich later.
        return "Uganda"

    def get_is_favorited(self, obj):
        req = self.context.get("request")
        if not req or not req.user or not req.user.is_authenticated:
            return False
        # After we add favorites app, this will work without extra queries:
        # return obj.favorited_by.filter(user=req.user).exists()
        # For now (before the app exists), always False:
        return False

    class Meta:
        model = Listing
        fields = "__all__"
