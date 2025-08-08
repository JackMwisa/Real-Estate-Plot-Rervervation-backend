from django.contrib import admin
from .models import Listing, Poi

@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "listing_type", "property_status", "date_posted")
    list_filter = ("listing_type", "property_status", "area", "date_posted")
    search_fields = ("title", "borough", "agent_name", "agent_phone")

@admin.register(Poi)
class PoiAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude")
    search_fields = ("name",)
