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
from .models import VisitSlot, Visit, VisitReminderTask

User = get_user_model()


class VisitModelTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@example.com',
            password='testpass123'
        )
        
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=self.agent
        )

    def test_visit_slot_creation(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=3,
            fee_amount=Decimal('10.00')
        )
        
        self.assertEqual(slot.available_capacity, 3)
        self.assertFalse(slot.is_full)
        self.assertFalse(slot.is_past)

    def test_visit_creation(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=2
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            visitor_count=1
        )
        
        self.assertEqual(visit.status, 'requested')
        self.assertEqual(slot.available_capacity, 1)
        self.assertFalse(visit.can_checkin)

    def test_visit_confirmation_generates_checkin_code(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot
        )
        
        # Confirm visit
        visit.status = 'confirmed'
        visit.save()
        
        self.assertIsNotNone(visit.checkin_code)
        self.assertEqual(len(visit.checkin_code), 6)
        self.assertIsNotNone(visit.confirmed_at)

    def test_checkin_availability(self):
        # Create slot starting in 10 minutes
        start_time = timezone.now() + timedelta(minutes=10)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed'
        )
        
        # Should be able to check in (15 min window before start)
        self.assertTrue(visit.can_checkin)

    def test_capacity_enforcement(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=1
        )
        
        # First visit
        Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed'
        )
        
        self.assertEqual(slot.available_capacity, 0)
        self.assertTrue(slot.is_full)


class VisitAPITests(APITestCase):
    def setUp(self):
        self.agent = User.objects.create_user(
            username='agent',
            email='agent@example.com',
            password='testpass123'
        )
        
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=self.agent
        )

    def test_create_visit_slot(self):
        self.client.force_authenticate(user=self.agent)
        
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        url = reverse('visit-slot-list')
        data = {
            'listing': self.listing.id,
            'start_at': start_time.isoformat(),
            'end_at': end_time.isoformat(),
            'capacity': 3,
            'fee_amount': '10.00'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(VisitSlot.objects.count(), 1)
        
        slot = VisitSlot.objects.first()
        self.assertEqual(slot.agent, self.agent)
        self.assertEqual(slot.capacity, 3)

    def test_request_visit(self):
        # Create slot
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=2
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('visit-list')
        data = {
            'slot': str(slot.id),
            'visitor_count': 1,
            'special_requests': 'Please show the kitchen first'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Visit.objects.count(), 1)
        
        visit = Visit.objects.first()
        self.assertEqual(visit.buyer, self.buyer)
        self.assertEqual(visit.status, 'requested')

    def test_confirm_visit(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot
        )
        
        self.client.force_authenticate(user=self.agent)
        
        url = reverse('visit-confirm', kwargs={'pk': visit.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'confirmed')
        self.assertIn('checkin_code', response.data)
        
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'confirmed')
        self.assertIsNotNone(visit.checkin_code)

    def test_checkin_visit(self):
        start_time = timezone.now() + timedelta(minutes=10)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed',
            checkin_code='ABC123'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('visit-checkin', kwargs={'pk': visit.id})
        data = {
            'checkin_code': 'ABC123',
            'location': {'lat': 0.3136, 'lng': 32.5811}
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'checked_in')
        
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'checked_in')
        self.assertIsNotNone(visit.checkin_at)

    def test_invalid_checkin_code(self):
        start_time = timezone.now() + timedelta(minutes=10)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed',
            checkin_code='ABC123'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('visit-checkin', kwargs={'pk': visit.id})
        data = {'checkin_code': 'WRONG1'}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid check-in code', str(response.data))

    def test_submit_feedback(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='completed'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('visit-feedback', kwargs={'pk': visit.id})
        data = {
            'rating': 5,
            'feedback': 'Great property and excellent service!'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        visit.refresh_from_db()
        self.assertEqual(visit.buyer_rating, 5)
        self.assertEqual(visit.buyer_feedback, 'Great property and excellent service!')

    def test_capacity_validation(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=1
        )
        
        # First visit (should succeed)
        Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed'
        )
        
        # Second user tries to book (should fail)
        other_buyer = User.objects.create_user(
            username='buyer2',
            email='buyer2@example.com',
            password='testpass123'
        )
        
        self.client.force_authenticate(user=other_buyer)
        
        url = reverse('visit-list')
        data = {
            'slot': str(slot.id),
            'visitor_count': 1
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fully booked', str(response.data))

    def test_permission_checks(self):
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot
        )
        
        # Other user should not be able to confirm visit
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='testpass123'
        )
        
        self.client.force_authenticate(user=other_user)
        
        url = reverse('visit-confirm', kwargs={'pk': visit.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upcoming_visits(self):
        # Create future visit
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time
        )
        
        Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='confirmed'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('my-upcoming-visits')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_available_slots_for_listing(self):
        # Create available slot
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        VisitSlot.objects.create(
            listing=self.listing,
            agent=self.agent,
            start_at=start_time,
            end_at=end_time,
            capacity=2,
            is_active=True
        )
        
        url = f'/api/listings/{self.listing.id}/available-slots/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['available_capacity'], 2)