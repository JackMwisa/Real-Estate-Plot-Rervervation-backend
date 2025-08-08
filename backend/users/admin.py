from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Profile

User = get_user_model()

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["seller", "agency_name", "phone_number"]
    search_fields = ["seller__username", "agency_name", "phone_number"]
