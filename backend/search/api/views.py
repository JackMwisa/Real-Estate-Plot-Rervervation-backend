from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from ..models import SavedSearch
from ..services import SearchService, SavedSearchService
from .serializers import SavedSearchSerializer


class SearchView(generics.GenericAPIView):
    """
    GET /api/search/
    Main search endpoint with filtering, sorting, and pagination
    """
    
    def get(self, request):
        search_service = SearchService()
        params = dict(request.query_params)
        
        # Convert single-item lists to strings for query params
        for key, value in params.items():
            if isinstance(value, list) and len(value) == 1:
                params[key] = value[0]
        
        results = search_service.search(params, user=request.user)
        return Response(results)


class SearchFacetsView(generics.GenericAPIView):
    """
    GET /api/search/facets/
    Get facet counts for current filter set
    """
    
    def get(self, request):
        search_service = SearchService()
        params = dict(request.query_params)
        
        # Convert single-item lists to strings
        for key, value in params.items():
            if isinstance(value, list) and len(value) == 1:
                params[key] = value[0]
        
        facets = search_service.get_facets(params)
        return Response(facets)


class SearchSuggestView(generics.GenericAPIView):
    """
    GET /api/search/suggest/
    Autosuggest endpoint for typeahead
    """
    
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        kind = request.query_params.get('kind', 'locations')
        limit = min(int(request.query_params.get('limit', 10)), 20)
        
        if not query:
            return Response({'suggestions': []})
        
        search_service = SearchService()
        suggestions = search_service.get_suggestions(query, kind, limit)
        
        return Response({'suggestions': suggestions})


class SavedSearchListCreateView(generics.ListCreateAPIView):
    """
    GET /api/search/saved/ - List user's saved searches
    POST /api/search/saved/ - Create new saved search
    """
    serializer_class = SavedSearchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SavedSearch.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # Get query params from request data
        query_params = self.request.data.get('query_params', {})
        name = self.request.data.get('name', 'Untitled Search')
        
        saved_search = SavedSearchService.create_saved_search(
            user=self.request.user,
            name=name,
            query_params=query_params
        )
        
        # Return the created object data
        serializer.instance = saved_search


class SavedSearchDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/search/saved/{id}/
    """
    serializer_class = SavedSearchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SavedSearch.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def enable_alerts(request, pk):
    """
    POST /api/search/saved/{id}/alerts/enable
    Enable alerts for a saved search
    """
    saved_search = get_object_or_404(
        SavedSearch, 
        pk=pk, 
        user=request.user
    )
    
    saved_search.alerts_enabled = True
    saved_search.save(update_fields=['alerts_enabled'])
    
    return Response({'status': 'enabled'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def disable_alerts(request, pk):
    """
    POST /api/search/saved/{id}/alerts/disable
    Disable alerts for a saved search
    """
    saved_search = get_object_or_404(
        SavedSearch, 
        pk=pk, 
        user=request.user
    )
    
    saved_search.alerts_enabled = False
    saved_search.save(update_fields=['alerts_enabled'])
    
    return Response({'status': 'disabled'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def run_saved_search(request, pk):
    """
    POST /api/search/saved/{id}/run
    Execute a saved search and return current results
    """
    saved_search = get_object_or_404(
        SavedSearch, 
        pk=pk, 
        user=request.user
    )
    
    results = SavedSearchService.run_saved_search(saved_search)
    return Response(results)