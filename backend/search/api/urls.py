from django.urls import path
from . import views

urlpatterns = [
    # Main search endpoints
    path('', views.SearchView.as_view(), name='search'),
    path('facets/', views.SearchFacetsView.as_view(), name='search-facets'),
    path('suggest/', views.SearchSuggestView.as_view(), name='search-suggest'),
    
    # Saved searches
    path('saved/', views.SavedSearchListCreateView.as_view(), name='saved-search-list'),
    path('saved/<int:pk>/', views.SavedSearchDetailView.as_view(), name='saved-search-detail'),
    path('saved/<int:pk>/run/', views.run_saved_search, name='saved-search-run'),
    path('saved/<int:pk>/alerts/enable/', views.enable_alerts, name='saved-search-enable-alerts'),
    path('saved/<int:pk>/alerts/disable/', views.disable_alerts, name='saved-search-disable-alerts'),
]