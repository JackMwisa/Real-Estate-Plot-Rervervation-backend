from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from unittest.mock import patch

from listings.models import Listing
from .models import TourAsset, TourAccessLog, TourTemplate

User = get_user_model()


class TourModelTests(TestCase):
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
            seller=self.user
        )

    def test_tour_asset_creation(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Virtual Tour',
            kind='3d',
            provider='matterport',
            url='https://my.matterport.com/show/?m=example',
            created_by=self.user
        )
        
        self.assertEqual(tour.title, 'Virtual Tour')
        self.assertEqual(tour.kind, '3d')
        self.assertEqual(tour.access_count, 0)
        self.assertTrue(tour.is_active)

    def test_embed_url_generation(self):
        # Test YouTube URL conversion
        youtube_tour = TourAsset.objects.create(
            listing=self.listing,
            title='YouTube Tour',
            kind='video',
            provider='youtube',
            url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            created_by=self.user
        )
        
        embed_url = youtube_tour.get_embed_url()
        self.assertEqual(embed_url, 'https://www.youtube.com/embed/dQw4w9WgXcQ')
        
        # Test Vimeo URL conversion
        vimeo_tour = TourAsset.objects.create(
            listing=self.listing,
            title='Vimeo Tour',
            kind='video',
            provider='vimeo',
            url='https://vimeo.com/123456789',
            created_by=self.user
        )
        
        embed_url = vimeo_tour.get_embed_url()
        self.assertEqual(embed_url, 'https://player.vimeo.com/video/123456789')

    def test_access_requirements_ungated(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Public Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            is_gated=False,
            created_by=self.user
        )
        
        allowed, reason = tour.check_access_requirements(self.user)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_access_requirements_gated_verified_user(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Gated Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            is_gated=True,
            access_requirements={'verified_user': True},
            created_by=self.user
        )
        
        # Without verification
        allowed, reason = tour.check_access_requirements(self.user)
        self.assertFalse(allowed)
        self.assertEqual(reason, "User verification required")

    def test_increment_access_count(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Test Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            created_by=self.user
        )
        
        initial_count = tour.access_count
        tour.increment_access_count()
        
        tour.refresh_from_db()
        self.assertEqual(tour.access_count, initial_count + 1)
        self.assertIsNotNone(tour.last_accessed_at)

    def test_tour_access_log_creation(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Test Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            created_by=self.user
        )
        
        log = TourAccessLog.objects.create(
            tour_asset=tour,
            user=self.user,
            access_method='direct',
            duration_seconds=120
        )
        
        self.assertEqual(log.tour_asset, tour)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.duration_seconds, 120)

    def test_tour_template_creation(self):
        template = TourTemplate.objects.create(
            name='Matterport 3D',
            provider='matterport',
            kind='3d',
            url_pattern='https://my.matterport.com/show/?m={tour_id}',
            embed_pattern='https://my.matterport.com/show/?m={tour_id}&play=1'
        )
        
        self.assertEqual(template.name, 'Matterport 3D')
        self.assertEqual(template.provider, 'matterport')
        self.assertTrue(template.is_active)


class TourAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='testpass123',
            is_staff=True
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=self.user
        )

    def test_create_tour_asset(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('tour-asset-list')
        data = {
            'listing': self.listing.id,
            'title': 'Virtual Tour',
            'description': 'Amazing 3D tour of the property',
            'kind': '3d',
            'provider': 'matterport',
            'url': 'https://my.matterport.com/show/?m=example',
            'is_gated': False
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TourAsset.objects.count(), 1)
        
        tour = TourAsset.objects.first()
        self.assertEqual(tour.title, 'Virtual Tour')
        self.assertEqual(tour.created_by, self.user)

    def test_list_tour_assets(self):
        # Create tours
        TourAsset.objects.create(
            listing=self.listing,
            title='Public Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour1',
            is_active=True,
            created_by=self.user
        )
        
        TourAsset.objects.create(
            listing=self.listing,
            title='Inactive Tour',
            kind='video',
            provider='youtube',
            url='https://youtube.com/watch?v=example',
            is_active=False,
            created_by=self.user
        )
        
        url = reverse('tour-asset-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Anonymous users should see only active tours
        self.assertEqual(len(response.data['results']), 1)

    def test_request_tour_access_public(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Public Tour',
            kind='3d',
            provider='matterport',
            url='https://my.matterport.com/show/?m=example',
            is_gated=False,
            created_by=self.user
        )
        
        url = reverse('tour-request-access', kwargs={'pk': tour.id})
        data = {
            'access_method': 'direct',
            'device_type': 'desktop'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['access_granted'])
        self.assertIn('tour_url', response.data)
        
        # Check access log was created
        self.assertEqual(TourAccessLog.objects.count(), 1)

    def test_request_tour_access_gated_denied(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Gated Tour',
            kind='3d',
            provider='matterport',
            url='https://my.matterport.com/show/?m=example',
            is_gated=True,
            access_requirements={'verified_user': True},
            created_by=self.user
        )
        
        url = reverse('tour-request-access', kwargs={'pk': tour.id})
        data = {'access_method': 'direct'}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['access_granted'])
        self.assertIn('reason', response.data)

    def test_listing_tours_summary(self):
        # Create different types of tours
        TourAsset.objects.create(
            listing=self.listing,
            title='3D Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/3d',
            is_active=True,
            created_by=self.user
        )
        
        TourAsset.objects.create(
            listing=self.listing,
            title='Video Tour',
            kind='video',
            provider='youtube',
            url='https://youtube.com/watch?v=example',
            is_active=True,
            created_by=self.user
        )
        
        TourAsset.objects.create(
            listing=self.listing,
            title='Gated Tour',
            kind='360',
            provider='custom',
            url='https://example.com/360',
            is_gated=True,
            is_active=True,
            created_by=self.user
        )
        
        url = f'/api/listings/{self.listing.id}/tours/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_tours'], 3)
        self.assertTrue(response.data['has_3d_tours'])
        self.assertTrue(response.data['has_video_tours'])
        self.assertTrue(response.data['has_360_photos'])
        self.assertEqual(response.data['gated_count'], 1)
        # Public tours should only include non-gated ones
        self.assertEqual(len(response.data['public_tours']), 2)

    def test_tour_providers_endpoint(self):
        url = reverse('tour-providers')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('providers', response.data)
        self.assertIn('tour_kinds', response.data)
        
        # Check provider structure
        providers = response.data['providers']
        self.assertGreater(len(providers), 0)
        
        matterport = next((p for p in providers if p['key'] == 'matterport'), None)
        self.assertIsNotNone(matterport)
        self.assertTrue(matterport['supports_embed'])
        self.assertTrue(matterport['supports_3d'])

    def test_permission_checks(self):
        # Other user should not be able to create tour for this listing
        self.client.force_authenticate(user=self.other_user)
        
        url = reverse('tour-asset-list')
        data = {
            'listing': self.listing.id,
            'title': 'Unauthorized Tour',
            'kind': '3d',
            'provider': 'matterport',
            'url': 'https://example.com/tour'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('You can only add tours to your own listings', str(response.data))

    def test_staff_permissions(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Test Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            created_by=self.user
        )
        
        # Staff should be able to update any tour
        self.client.force_authenticate(user=self.staff_user)
        
        url = reverse('tour-asset-detail', kwargs={'pk': tour.id})
        data = {'title': 'Updated by Staff'}
        
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        tour.refresh_from_db()
        self.assertEqual(tour.title, 'Updated by Staff')

    def test_tour_analytics_access(self):
        tour = TourAsset.objects.create(
            listing=self.listing,
            title='Test Tour',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour',
            created_by=self.user
        )
        
        # Create access log
        TourAccessLog.objects.create(
            tour_asset=tour,
            user=self.other_user,
            access_method='direct'
        )
        
        # Owner should be able to see analytics
        self.client.force_authenticate(user=self.user)
        
        url = reverse('tour-analytics', kwargs={'tour_id': tour.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Other user should not see analytics
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_bulk_update_tours_staff_only(self):
        tour1 = TourAsset.objects.create(
            listing=self.listing,
            title='Tour 1',
            kind='3d',
            provider='matterport',
            url='https://example.com/tour1',
            is_active=True,
            created_by=self.user
        )
        
        tour2 = TourAsset.objects.create(
            listing=self.listing,
            title='Tour 2',
            kind='video',
            provider='youtube',
            url='https://youtube.com/watch?v=example',
            is_active=True,
            created_by=self.user
        )
        
        # Regular user should not have access
        self.client.force_authenticate(user=self.user)
        
        url = reverse('bulk-update-tours')
        data = {
            'tour_ids': [str(tour1.id), str(tour2.id)],
            'updates': {'is_active': False}
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Staff should have access
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['updated_count'], 2)
        
        # Check tours were updated
        tour1.refresh_from_db()
        tour2.refresh_from_db()
        self.assertFalse(tour1.is_active)
        self.assertFalse(tour2.is_active)