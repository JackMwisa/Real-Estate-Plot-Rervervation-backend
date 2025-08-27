from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from listings.models import Listing
from .models import AdPackage, AdCampaign, AdImpression, AdClick, AdMetricsRollup
from .services import AdRankingService, AdBillingService, AdAnalyticsService

User = get_user_model()


class AdModelTests(TestCase):
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
        
        self.package = AdPackage.objects.create(
            name='Basic Package',
            sku='BASIC-001',
            duration_days=30,
            pricing_model='flat',
            price=Decimal('100.00'),
            max_boost_score=2.0
        )

    def test_ad_package_creation(self):
        self.assertEqual(self.package.name, 'Basic Package')
        self.assertEqual(self.package.sku, 'BASIC-001')
        self.assertFalse(self.package.is_performance_based)
        
        # Test performance-based package
        cpc_package = AdPackage.objects.create(
            name='CPC Package',
            sku='CPC-001',
            duration_days=30,
            pricing_model='cpc',
            price=Decimal('0.50')
        )
        self.assertTrue(cpc_package.is_performance_based)

    def test_ad_campaign_creation(self):
        start_date = timezone.now()
        end_date = start_date + timedelta(days=30)
        
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=start_date,
            end_at=end_date,
            budget=Decimal('500.00'),
            boost_score=1.5
        )
        
        self.assertEqual(campaign.owner, self.user)
        self.assertEqual(campaign.target_type, 'listing')
        self.assertEqual(campaign.status, 'draft')
        self.assertEqual(campaign.ctr, 0.0)
        self.assertEqual(campaign.cost_per_click, Decimal('0.00'))

    def test_campaign_can_serve_ad(self):
        start_date = timezone.now() - timedelta(days=1)
        end_date = timezone.now() + timedelta(days=29)
        
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=start_date,
            end_at=end_date,
            budget=Decimal('500.00'),
            status='active'
        )
        
        self.assertTrue(campaign.can_serve_ad())
        
        # Test budget exhausted
        campaign.spent_amount = Decimal('500.00')
        campaign.save()
        self.assertFalse(campaign.can_serve_ad())

    def test_campaign_get_target_object(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        target = campaign.get_target_object()
        self.assertEqual(target, self.listing)

    def test_ad_impression_creation(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        impression = AdImpression.objects.create(
            campaign=campaign,
            user=self.user,
            session_id='test-session',
            page_url='https://example.com/search',
            search_query='apartment kampala',
            position=1,
            cost=Decimal('0.10')
        )
        
        self.assertEqual(impression.campaign, campaign)
        self.assertEqual(impression.user, self.user)
        self.assertEqual(impression.position, 1)

    def test_ad_click_creation(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        impression = AdImpression.objects.create(
            campaign=campaign,
            user=self.user,
            session_id='test-session'
        )
        
        click = AdClick.objects.create(
            campaign=campaign,
            impression=impression,
            user=self.user,
            session_id='test-session',
            clicked_url='https://example.com/listing/1',
            cost=Decimal('0.50')
        )
        
        self.assertEqual(click.campaign, campaign)
        self.assertEqual(click.impression, impression)

    def test_metrics_rollup(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        rollup = AdMetricsRollup.objects.create(
            campaign=campaign,
            date=timezone.now().date(),
            impressions=1000,
            clicks=50,
            spend=Decimal('25.00')
        )
        
        self.assertEqual(rollup.ctr, 5.0)  # 50/1000 * 100
        self.assertEqual(rollup.cpc, Decimal('0.50'))  # 25.00/50


class AdServiceTests(TestCase):
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
        
        self.package = AdPackage.objects.create(
            name='Basic Package',
            sku='BASIC-001',
            duration_days=30,
            pricing_model='cpc',
            price=Decimal('0.50'),
            max_boost_score=2.0
        )

    def test_ad_ranking_service(self):
        # Create active campaign
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now() - timedelta(days=1),
            end_at=timezone.now() + timedelta(days=29),
            budget=Decimal('500.00'),
            status='active',
            boost_score=2.0
        )
        
        service = AdRankingService()
        
        # Test getting boost scores
        boost_map = service.get_active_campaigns_for_listings([self.listing.id])
        self.assertEqual(boost_map[self.listing.id], 2.0)
        
        # Test score blending
        organic_score = 1.0
        boost_score = 2.0
        blended = service.blend_scores(organic_score, boost_score)
        self.assertGreater(blended, organic_score)
        
        # Test applying ranking boost
        search_results = [
            {'id': self.listing.id, '_score': 1.0, 'title': 'Test Listing'}
        ]
        boosted_results = service.apply_ranking_boost(search_results)
        
        self.assertTrue(boosted_results[0]['_boosted'])
        self.assertEqual(boosted_results[0]['_boost_score'], 2.0)
        self.assertGreater(boosted_results[0]['_score'], 1.0)

    def test_ad_billing_service(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        # Test CPC cost calculation
        click_cost = AdBillingService.calculate_click_cost(campaign)
        self.assertEqual(click_cost, Decimal('0.50'))
        
        # Test impression cost (should be 0 for CPC)
        impression_cost = AdBillingService.calculate_impression_cost(campaign)
        self.assertEqual(impression_cost, Decimal('0.00'))
        
        # Test spend update
        initial_spend = campaign.spent_amount
        AdBillingService.update_campaign_spend(campaign, Decimal('10.00'))
        campaign.refresh_from_db()
        self.assertEqual(campaign.spent_amount, initial_spend + Decimal('10.00'))

    def test_ad_analytics_service(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00'),
            impressions=1000,
            clicks=50,
            spent_amount=Decimal('25.00')
        )
        
        # Create some test events
        AdImpression.objects.create(
            campaign=campaign,
            cost=Decimal('0.01')
        )
        AdClick.objects.create(
            campaign=campaign,
            cost=Decimal('0.50')
        )
        
        performance = AdAnalyticsService.get_campaign_performance(campaign)
        
        self.assertEqual(performance['impressions'], 1)
        self.assertEqual(performance['clicks'], 1)
        self.assertEqual(performance['total_cost'], Decimal('0.51'))
        self.assertEqual(performance['budget_utilization'], 5.0)  # 25/500 * 100


class AdAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='staffpass123',
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
        
        self.package = AdPackage.objects.create(
            name='Basic Package',
            sku='BASIC-001',
            duration_days=30,
            pricing_model='flat',
            price=Decimal('100.00'),
            max_boost_score=2.0
        )

    def test_ad_package_list(self):
        url = reverse('ad-package-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Basic Package')

    def test_create_campaign(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('ad-campaign-list')
        data = {
            'package': self.package.id,
            'target_type': 'listing',
            'target_id': self.listing.id,
            'start_at': timezone.now().isoformat(),
            'end_at': (timezone.now() + timedelta(days=30)).isoformat(),
            'budget': '500.00',
            'boost_score': 1.5,
            'notes': 'Test campaign'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check campaign was created
        campaign = AdCampaign.objects.get(id=response.data['id'])
        self.assertEqual(campaign.owner, self.user)
        self.assertEqual(campaign.target_type, 'listing')
        self.assertEqual(campaign.status, 'draft')

    def test_campaign_permissions(self):
        # Create campaign for user1
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        # Create another user
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='pass123'
        )
        
        # Other user should not see the campaign
        self.client.force_authenticate(user=other_user)
        url = reverse('ad-campaign-detail', kwargs={'pk': campaign.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Staff should see all campaigns
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_campaign_metrics(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00')
        )
        
        # Create some test metrics
        AdMetricsRollup.objects.create(
            campaign=campaign,
            date=timezone.now().date(),
            impressions=1000,
            clicks=50,
            spend=Decimal('25.00')
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('ad-campaign-metrics', kwargs={'pk': campaign.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_impressions'], 1000)
        self.assertEqual(response.data['total_clicks'], 50)

    def test_pause_resume_campaign(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00'),
            status='active'
        )
        
        self.client.force_authenticate(user=self.user)
        
        # Pause campaign
        pause_url = reverse('ad-campaign-pause', kwargs={'pk': campaign.id})
        response = self.client.post(pause_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'paused')
        
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'paused')
        
        # Resume campaign
        resume_url = reverse('ad-campaign-resume', kwargs={'pk': campaign.id})
        response = self.client.post(resume_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'active')
        
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'active')

    def test_track_ad_event(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now() - timedelta(days=1),
            end_at=timezone.now() + timedelta(days=29),
            budget=Decimal('500.00'),
            status='active'
        )
        
        url = reverse('ad-track-event')
        
        # Track impression
        impression_data = {
            'campaign_id': str(campaign.id),
            'event_type': 'impression',
            'page_url': 'https://example.com/search',
            'search_query': 'apartment kampala',
            'position': 1
        }
        
        response = self.client.post(url, impression_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['event_type'], 'impression')
        
        # Check impression was created
        impression = AdImpression.objects.get(id=response.data['impression_id'])
        self.assertEqual(impression.campaign, campaign)
        self.assertEqual(impression.position, 1)
        
        # Track click
        click_data = {
            'campaign_id': str(campaign.id),
            'event_type': 'click',
            'clicked_url': 'https://example.com/listing/1',
            'referrer_url': 'https://example.com/search'
        }
        
        response = self.client.post(url, click_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['event_type'], 'click')
        
        # Check click was created
        click = AdClick.objects.get(id=response.data['click_id'])
        self.assertEqual(click.campaign, campaign)

    def test_staff_campaign_approval(self):
        campaign = AdCampaign.objects.create(
            owner=self.user,
            package=self.package,
            target_type='listing',
            target_id=self.listing.id,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
            budget=Decimal('500.00'),
            status='pending'
        )
        
        self.client.force_authenticate(user=self.staff_user)
        
        # Approve campaign
        approve_url = reverse('staff-approve-campaign', kwargs={'pk': campaign.id})
        response = self.client.post(approve_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')
        
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'active')
        self.assertIsNotNone(campaign.approved_at)
        self.assertEqual(campaign.approved_by, self.staff_user)

    def test_validation_errors(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('ad-campaign-list')
        
        # Test invalid date range
        data = {
            'package': self.package.id,
            'target_type': 'listing',
            'target_id': self.listing.id,
            'start_at': timezone.now().isoformat(),
            'end_at': (timezone.now() - timedelta(days=1)).isoformat(),  # End before start
            'budget': '500.00',
            'boost_score': 1.5
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', str(response.data))
        
        # Test non-existent listing
        data['end_at'] = (timezone.now() + timedelta(days=30)).isoformat()
        data['target_id'] = 99999  # Non-existent listing
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Listing does not exist', str(response.data))