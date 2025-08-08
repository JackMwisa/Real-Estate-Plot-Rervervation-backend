from rest_framework import serializers
from users.models import Profile
from listings.models import Listing
from listings.api.serializers import ListingSerializer  # note the api path

class ProfileSerializer(serializers.ModelSerializer):
    seller_username = serializers.SerializerMethodField()
    seller_email = serializers.SerializerMethodField()
    seller_listings = serializers.SerializerMethodField()

    def get_seller_username(self, obj):
        return obj.seller.username

    def get_seller_email(self, obj):
        return obj.seller.email

    def get_seller_listings(self, obj):
        qs = Listing.objects.filter(seller=obj.seller).order_by("-date_posted")
        return ListingSerializer(qs, many=True).data

    class Meta:
        model = Profile
        fields = "__all__"
