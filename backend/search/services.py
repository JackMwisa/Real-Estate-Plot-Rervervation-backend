import time
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from django.db.models import Q, Count, Min, Max
from django.contrib.postgres.search import TrigramSimilarity
from django.conf import settings
from django.utils import timezone
from listings.models import Listing
from users.models import Profile
from .models import SearchEvent, SavedSearch


class SearchService:
    """Core search service with PostgreSQL backend"""
    
    def __init__(self):
        self.max_page_size = getattr(settings, 'SEARCH_MAX_PAGE_SIZE', 50)
        self.default_sort = getattr(settings, 'SEARCH_DEFAULT_SORT', 'relevance')
        self.rank_weights = getattr(settings, 'SEARCH_RANK_WEIGHTS', {
            'text_relevance': 1.0,
            'freshness': 0.3,
            'verified': 0.2,
            'media_richness': 0.1,
            'distance': 0.4
        })

    def search(self, params: Dict[str, Any], user=None) -> Dict[str, Any]:
        """Main search method"""
        start_time = time.time()
        
        # Build base queryset
        queryset = self._build_queryset(params)
        
        # Apply sorting
        queryset = self._apply_sorting(queryset, params)
        
        # Get total count before pagination
        total_count = queryset.count()
        
        # Apply pagination
        page = int(params.get('page', 1))
        page_size = min(int(params.get('page_size', 20)), self.max_page_size)
        offset = (page - 1) * page_size
        
        results = queryset[offset:offset + page_size]
        
        # Calculate timing
        took_ms = int((time.time() - start_time) * 1000)
        
        # Log search event
        self._log_search_event(params, total_count, took_ms, user)
        
        return {
            'results': list(results.values()),
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'took_ms': took_ms
        }

    def _build_queryset(self, params: Dict[str, Any]):
        """Build filtered queryset based on search parameters"""
        queryset = Listing.objects.select_related('seller', 'seller__profile')
        
        # Text search
        q = params.get('q', '').strip()
        if q:
            if hasattr(settings, 'DATABASES') and 'postgresql' in settings.DATABASES['default']['ENGINE']:
                # Use trigram similarity for PostgreSQL
                queryset = queryset.annotate(
                    similarity=TrigramSimilarity('title', q) + 
                              TrigramSimilarity('description', q) + 
                              TrigramSimilarity('borough', q)
                ).filter(similarity__gt=0.1)
            else:
                # Fallback for SQLite
                queryset = queryset.filter(
                    Q(title__icontains=q) |
                    Q(description__icontains=q) |
                    Q(borough__icontains=q)
                )
        
        # Status filter (default to available)
        status = params.get('status', 'available')
        if status:
            queryset = queryset.filter(property_status=status)
        
        # Type filter
        listing_type = params.get('type')
        if listing_type:
            queryset = queryset.filter(listing_type=listing_type)
        
        # Price filters
        price_min = params.get('price_min')
        if price_min:
            queryset = queryset.filter(price__gte=Decimal(price_min))
        
        price_max = params.get('price_max')
        if price_max:
            queryset = queryset.filter(price__lte=Decimal(price_max))
        
        # Room filters
        rooms_min = params.get('rooms_min')
        if rooms_min:
            queryset = queryset.filter(bedrooms__gte=int(rooms_min))
        
        rooms_max = params.get('rooms_max')
        if rooms_max:
            queryset = queryset.filter(bedrooms__lte=int(rooms_max))
        
        # Size filters
        size_min = params.get('size_min')
        if size_min:
            queryset = queryset.filter(area_size__gte=Decimal(size_min))
        
        size_max = params.get('size_max')
        if size_max:
            queryset = queryset.filter(area_size__lte=Decimal(size_max))
        
        # Amenities filter
        amenities = params.get('amenities', [])
        if isinstance(amenities, str):
            amenities = amenities.split(',')
        
        for amenity in amenities:
            amenity = amenity.strip().lower()
            if amenity == 'pool':
                queryset = queryset.filter(pool=True)
            elif amenity == 'parking':
                queryset = queryset.filter(parking=True)
            elif amenity == 'garden':
                queryset = queryset.filter(garden=True)
            elif amenity == 'elevator':
                queryset = queryset.filter(elevator=True)
            elif amenity == 'cctv':
                queryset = queryset.filter(cctv=True)
            elif amenity == 'furnished':
                queryset = queryset.filter(furnished=True)
        
        # Geo filters
        bbox = params.get('bbox')
        if bbox:
            try:
                minx, miny, maxx, maxy = map(float, bbox.split(','))
                queryset = queryset.filter(
                    longitude__gte=minx,
                    longitude__lte=maxx,
                    latitude__gte=miny,
                    latitude__lte=maxy
                )
            except (ValueError, TypeError):
                pass
        
        # Radius filter
        lat = params.get('lat')
        lng = params.get('lng')
        radius_km = params.get('radius_km')
        
        if lat and lng and radius_km:
            try:
                lat, lng, radius_km = float(lat), float(lng), float(radius_km)
                # Simple bounding box approximation for radius
                lat_delta = radius_km / 111.0  # ~111km per degree latitude
                lng_delta = radius_km / (111.0 * abs(lat) * 0.01745329252)  # Adjust for longitude
                
                queryset = queryset.filter(
                    latitude__gte=lat - lat_delta,
                    latitude__lte=lat + lat_delta,
                    longitude__gte=lng - lng_delta,
                    longitude__lte=lng + lng_delta
                )
            except (ValueError, TypeError):
                pass
        
        return queryset

    def _apply_sorting(self, queryset, params: Dict[str, Any]):
        """Apply sorting to queryset"""
        sort = params.get('sort', self.default_sort)
        
        if sort == 'newest':
            return queryset.order_by('-date_posted', '-created_at')
        elif sort == 'price_asc':
            return queryset.order_by('price', '-date_posted')
        elif sort == 'price_desc':
            return queryset.order_by('-price', '-date_posted')
        elif sort == 'relevance':
            # For text search, use similarity if available
            if hasattr(queryset.model, 'similarity'):
                return queryset.order_by('-similarity', '-date_posted')
            else:
                return queryset.order_by('-date_posted')
        elif sort == 'distance':
            # For now, just order by date if no distance calculation
            return queryset.order_by('-date_posted')
        else:
            return queryset.order_by('-date_posted')

    def get_facets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get facet counts for current search"""
        # Build base queryset with filters
        queryset = self._build_queryset(params)
        
        facets = {}
        
        # Type facets
        facets['types'] = list(
            queryset.values('listing_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Status facets
        facets['statuses'] = list(
            queryset.values('property_status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Area facets
        facets['areas'] = list(
            queryset.values('area')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Borough facets
        facets['boroughs'] = list(
            queryset.exclude(borough__isnull=True)
            .exclude(borough='')
            .values('borough')
            .annotate(count=Count('id'))
            .order_by('-count')[:20]
        )
        
        # Price ranges
        price_stats = queryset.aggregate(
            min_price=Min('price'),
            max_price=Max('price')
        )
        
        if price_stats['min_price'] and price_stats['max_price']:
            facets['price_range'] = {
                'min': float(price_stats['min_price']),
                'max': float(price_stats['max_price'])
            }
        
        # Amenities counts
        facets['amenities'] = {
            'pool': queryset.filter(pool=True).count(),
            'parking': queryset.filter(parking=True).count(),
            'garden': queryset.filter(garden=True).count(),
            'elevator': queryset.filter(elevator=True).count(),
            'cctv': queryset.filter(cctv=True).count(),
            'furnished': queryset.filter(furnished=True).count(),
        }
        
        return facets

    def get_suggestions(self, query: str, kind: str = 'locations', limit: int = 10) -> List[Dict[str, Any]]:
        """Get autosuggest results"""
        query = query.strip().lower()
        if not query:
            return []
        
        suggestions = []
        
        if kind == 'locations':
            # Get distinct locations
            locations = (
                Listing.objects
                .exclude(borough__isnull=True)
                .exclude(borough='')
                .filter(borough__icontains=query)
                .values('borough')
                .annotate(count=Count('id'))
                .order_by('-count')[:limit]
            )
            
            for loc in locations:
                suggestions.append({
                    'text': loc['borough'],
                    'type': 'location',
                    'count': loc['count']
                })
        
        elif kind == 'listings':
            # Get matching listings by title
            listings = (
                Listing.objects
                .filter(title__icontains=query)
                .values('id', 'title', 'price')
                .order_by('-date_posted')[:limit]
            )
            
            for listing in listings:
                suggestions.append({
                    'text': listing['title'],
                    'type': 'listing',
                    'id': listing['id'],
                    'price': float(listing['price'])
                })
        
        elif kind == 'agencies':
            # Get matching agencies
            agencies = (
                Profile.objects
                .exclude(agency_name__isnull=True)
                .exclude(agency_name='')
                .filter(agency_name__icontains=query)
                .values('agency_name')
                .annotate(count=Count('seller__listings'))
                .order_by('-count')[:limit]
            )
            
            for agency in agencies:
                suggestions.append({
                    'text': agency['agency_name'],
                    'type': 'agency',
                    'count': agency['count']
                })
        
        return suggestions

    def _log_search_event(self, params: Dict[str, Any], result_count: int, took_ms: int, user=None):
        """Log search event for analytics"""
        # Clean sensitive data from params
        clean_params = {k: v for k, v in params.items() if k not in ['csrfmiddlewaretoken']}
        
        SearchEvent.objects.create(
            user=user if user and user.is_authenticated else None,
            query_json=clean_params,
            result_count=result_count,
            took_ms=took_ms,
            source='api'
        )


class SavedSearchService:
    """Service for managing saved searches and alerts"""
    
    @staticmethod
    def create_saved_search(user, name: str, query_params: Dict[str, Any]) -> SavedSearch:
        """Create a new saved search"""
        # Clean and normalize query params
        clean_params = {k: v for k, v in query_params.items() 
                       if k not in ['page', 'page_size', 'csrfmiddlewaretoken']}
        
        saved_search, created = SavedSearch.objects.update_or_create(
            user=user,
            name=name,
            defaults={'query_json': clean_params}
        )
        
        return saved_search
    
    @staticmethod
    def run_saved_search(saved_search: SavedSearch) -> Dict[str, Any]:
        """Execute a saved search and return results"""
        search_service = SearchService()
        results = search_service.search(saved_search.query_json)
        
        # Update last run time
        saved_search.last_run_at = timezone.now()
        saved_search.save(update_fields=['last_run_at'])
        
        return results
    
    @staticmethod
    def get_new_matches_since_last_run(saved_search: SavedSearch) -> List[Listing]:
        """Get new listings that match the saved search since last run"""
        if not saved_search.last_run_at:
            return []
        
        search_service = SearchService()
        queryset = search_service._build_queryset(saved_search.query_json)
        
        # Only get listings created/updated since last run
        new_listings = queryset.filter(
            Q(created_at__gt=saved_search.last_run_at) |
            Q(updated_at__gt=saved_search.last_run_at)
        ).order_by('-created_at')
        
        return list(new_listings[:50])  # Limit to 50 new matches