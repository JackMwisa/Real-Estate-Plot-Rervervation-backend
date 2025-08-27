from django.contrib import admin
from .models import SavedSearch, SearchEvent, SearchIndexState


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "alerts_enabled", "last_run_at", "created_at")
    list_filter = ("alerts_enabled", "created_at", "last_run_at")
    search_fields = ("name", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SearchEvent)
class SearchEventAdmin(admin.ModelAdmin):
    list_display = ("user", "result_count", "took_ms", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at",)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SearchIndexState)
class SearchIndexStateAdmin(admin.ModelAdmin):
    list_display = ("index_name", "version", "last_sync_at", "updated_at")
    list_filter = ("last_sync_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")