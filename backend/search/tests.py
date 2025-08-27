from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from listings.models import Listing
from users.models import Profile
from .models import SavedSearch, SearchEvent
from .services import SearchService, SavedSearchService

User = get_user_model()


class SearchServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test listings
        self.listing1 = Listing.objects.create(
            title='Modern Apartment in Kampala',
            description='Beautiful apartment with great views',
            price=Decimal('1500.00'),
            listing_type='apartment',
            property_status='available',
            borough='Kampala',
            bedrooms=2,
            bathrooms=2,
            furnished=True,
            pool=True,
            seller=self.user
        )
        
        self.listing2 = Listing.objects.create(
            title='House in Entebbe',
            description='Spacious family house near the lake',
            price=Decimal('2500.00'),
            listing_type='house',
            property_status='available',
            borough='Entebbe',
            bedrooms=3,
            bathrooms=2,
            garden=True,
            parking=True,
            seller=self.user
        )

    def test_basic_search(self):
        search_service = SearchService()
        results = search_service.search({'q': 'apartment'})
        
        self.assertEqual(results['total_count'], 1)
        self.assertEqual(len(results['results']), 1)

    def test_price_filter(self):
        search_service = SearchService()
        results = search_service.search({
            'price_min': '2000',
            'price_max': '3000'
        })
        
        self.assertEqual(results['total_count'], 1)
        self.assertEqual(results['results'][0]['title'], 'House in Entebbe')

    def test_amenities_filter(self):
        search_service = SearchService()
        results = search_service.search({'amenities': 'pool,furnished'})
        
        self.assertEqual(results['total_count'], 1)
        self.assertEqual(results['results'][0]['title'], 'Modern Apartment in Kampala')

    def test_facets(self):
        search_service = SearchService()
        facets = search_service.get_facets({})
        
        self.assertIn('types', facets)
        self.assertIn('statuses', facets)
        self.assertIn('amenities', facets)
        
        # Check type facets
        type_counts = {item['listing_type']: item['count'] for item in facets['types']}
        self.assertEqual(type_counts.get('apartment'), 1)
        self.assertEqual(type_counts.get('house'), 1)

    def test_suggestions(self):
        search_service = SearchService()
        
        # Location suggestions
        suggestions = search_service.get_suggestions('kam', 'locations')
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['text'], 'Kampala')
        
        # Listing suggestions
        suggestions = search_service.get_suggestions('modern', 'listings')
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['text'], 'Modern Apartment in Kampala')


class SearchAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            borough='Test Borough',
            seller=self.user
        )

    def test_search_endpoint(self):
        url = reverse('search')
        response = self.client.get(url, {'q': 'test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_count'], 1)

    def test_facets_endpoint(self):
        url = reverse('search-facets')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('types', response.data)
        self.assertIn('amenities', response.data)

    def test_suggest_endpoint(self):
        url = reverse('search-suggest')
        response = self.client.get(url, {'q': 'test', 'kind': 'locations'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('suggestions', response.data)

    def test_saved_search_crud(self):
        self.client.force_authenticate(user=self.user)
        
        # Create saved search
        url = reverse('saved-search-list')
        data = {
            'name': 'My Search',
            'query_params': {'q': 'apartment', 'price_max': '2000'}
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # List saved searches
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        
        # Get saved search detail
        saved_search_id = response.data[0]['id']
        detail_url = reverse('saved-search-detail', kwargs={'pk': saved_search_id})
        response = self.client.get(detail_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'My Search')

    def test_enable_disable_alerts(self):
        self.client.force_authenticate(user=self.user)
        
        # Create saved search
        saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query_json={'q': 'test'}
        )
        
        # Enable alerts
        url = reverse('saved-search-enable-alerts', kwargs={'pk': saved_search.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'enabled')
        
        saved_search.refresh_from_db()
        self.assertTrue(saved_search.alerts_enabled)
        
        # Disable alerts
        url = reverse('saved-search-disable-alerts', kwargs={'pk': saved_search.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'disabled')
        
        saved_search.refresh_from_db()
        self.assertFalse(saved_search.alerts_enabled)


class SavedSearchServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_create_saved_search(self):
        query_params = {'q': 'apartment', 'price_max': '2000'}
        saved_search = SavedSearchService.create_saved_search(
            user=self.user,
            name='My Search',
            query_params=query_params
        )
        
        self.assertEqual(saved_search.name, 'My Search')
        self.assertEqual(saved_search.query_json, query_params)
        self.assertEqual(saved_search.user, self.user)

    def test_run_saved_search(self):
        saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query_json={'q': 'test'}
        )
        
        results = SavedSearchService.run_saved_search(saved_search)
        
        self.assertIn('results', results)
        self.assertIn('total_count', results)
        
        saved_search.refresh_from_db()
        self.assertIsNotNone(saved_search.last_run_at)