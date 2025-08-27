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
from visits.models import VisitSlot, Visit
from .models import Reservation, DisputeCase, ReservationPolicy
from .services import EscrowService, ReservationPolicyService, DisputeService

User = get_user_model()


class ReservationModelTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=self.seller
        )

    def test_reservation_creation(self):
        start_date = timezone.now() + timedelta(days=1)
        end_date = start_date + timedelta(days=7)
        
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            reservation_type='rental',
            start_at=start_date,
            end_at=end_date,
            amount=Decimal('1000.00'),
            security_deposit=Decimal('200.00')
        )
        
        self.assertEqual(reservation.escrow_state, 'initiated')
        self.assertEqual(reservation.total_amount, Decimal('1200.00'))
        self.assertTrue(reservation.is_pending)
        self.assertFalse(reservation.is_completed)
        self.assertTrue(reservation.can_cancel)

    def test_reservation_state_properties(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='confirmed',
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=1)
        )
        
        self.assertTrue(reservation.is_active)
        self.assertFalse(reservation.is_pending)
        self.assertTrue(reservation.can_dispute)

    def test_refund_calculation(self):
        start_date = timezone.now() + timedelta(days=10)
        end_date = start_date + timedelta(days=7)
        
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            start_at=start_date,
            end_at=end_date,
            amount=Decimal('1000.00'),
            escrow_state='paid',
            policy={
                'cancellation': {
                    'full_refund_days': 7,
                    'partial_refund_days': 3,
                    'partial_refund_percent': 50
                }
            }
        )
        
        # Should get full refund (10 days before start)
        refund = reservation.calculate_refund_amount()
        self.assertEqual(refund, Decimal('1000.00'))

    def test_dispute_case_creation(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='confirmed'
        )
        
        dispute = DisputeCase.objects.create(
            reservation=reservation,
            dispute_type='property_condition',
            opener=self.buyer,
            title='Property not as described',
            description='The property has issues not mentioned in the listing'
        )
        
        self.assertEqual(dispute.status, 'open')
        self.assertTrue(dispute.is_open)
        self.assertFalse(dispute.is_resolved)

    def test_reservation_policy(self):
        policy = ReservationPolicy.objects.create(
            name='Standard Policy',
            full_refund_days=7,
            partial_refund_days=3,
            partial_refund_percent=50,
            security_deposit_percent=20
        )
        
        security_deposit = policy.calculate_security_deposit(Decimal('1000.00'))
        self.assertEqual(security_deposit, Decimal('200.00'))
        
        policy_json = policy.to_policy_json()
        self.assertEqual(policy_json['cancellation']['full_refund_days'], 7)


class EscrowServiceTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=self.seller
        )

    def test_initiate_escrow(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00')
        )
        
        escrow_data = EscrowService.initiate_escrow(reservation)
        
        self.assertIn('escrow_reference', escrow_data)
        self.assertEqual(escrow_data['amount'], Decimal('1000.00'))
        self.assertIn('payment_url', escrow_data)

    def test_payment_webhook_processing(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00')
        )
        
        payment_data = {
            'status': 'successful',
            'reference': 'PAY-123456'
        }
        
        result = EscrowService.process_payment_webhook(str(reservation.id), payment_data)
        
        self.assertTrue(result)
        reservation.refresh_from_db()
        self.assertEqual(reservation.escrow_state, 'paid')

    def test_release_escrow(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='confirmed'
        )
        
        result = EscrowService.release_escrow(reservation)
        
        self.assertEqual(result['status'], 'released')
        self.assertEqual(result['amount'], Decimal('1000.00'))
        
        reservation.refresh_from_db()
        self.assertEqual(reservation.escrow_state, 'released')

    def test_refund_escrow(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='paid'
        )
        
        result = EscrowService.refund_escrow(
            reservation, 
            amount=Decimal('800.00'), 
            reason='Cancellation'
        )
        
        self.assertEqual(result['status'], 'refunded')
        self.assertEqual(result['amount'], Decimal('800.00'))
        
        reservation.refresh_from_db()
        self.assertEqual(reservation.escrow_state, 'refunded')


class BookingsAPITests(APITestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
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
            seller=self.seller
        )

    def test_create_reservation(self):
        self.client.force_authenticate(user=self.buyer)
        
        start_date = timezone.now() + timedelta(days=1)
        end_date = start_date + timedelta(days=7)
        
        url = reverse('reservation-list')
        data = {
            'listing': self.listing.id,
            'reservation_type': 'rental',
            'start_at': start_date.isoformat(),
            'end_at': end_date.isoformat(),
            'amount': '1000.00',
            'security_deposit': '200.00'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Reservation.objects.count(), 1)
        
        reservation = Reservation.objects.first()
        self.assertEqual(reservation.buyer, self.buyer)
        self.assertEqual(reservation.escrow_state, 'initiated')

    def test_confirm_reservation(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='paid'
        )
        
        self.client.force_authenticate(user=self.seller)
        
        url = reverse('reservation-confirm', kwargs={'pk': reservation.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'confirmed')
        
        reservation.refresh_from_db()
        self.assertEqual(reservation.escrow_state, 'confirmed')
        self.assertIsNotNone(reservation.confirmed_at)

    def test_cancel_reservation(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='paid',
            start_at=timezone.now() + timedelta(days=10),
            policy={
                'cancellation': {
                    'full_refund_days': 7,
                    'partial_refund_days': 3,
                    'partial_refund_percent': 50
                }
            }
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('reservation-cancel', kwargs={'pk': reservation.id})
        data = {'reason': 'Change of plans'}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')
        
        reservation.refresh_from_db()
        self.assertEqual(reservation.escrow_state, 'refunded')  # Should be refunded due to policy

    def test_create_dispute(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='confirmed'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('dispute-list', kwargs={'reservation_id': reservation.id})
        data = {
            'dispute_type': 'property_condition',
            'title': 'Property issues',
            'description': 'The property has several issues not mentioned in the listing',
            'evidence_json': {
                'photos': ['photo1.jpg', 'photo2.jpg'],
                'notes': 'Detailed notes about issues'
            }
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DisputeCase.objects.count(), 1)
        
        dispute = DisputeCase.objects.first()
        self.assertEqual(dispute.opener, self.buyer)
        self.assertEqual(dispute.status, 'investigating')  # Auto-assigned

    def test_resolve_dispute_staff_only(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='disputed'
        )
        
        dispute = DisputeCase.objects.create(
            reservation=reservation,
            dispute_type='property_condition',
            opener=self.buyer,
            title='Test Dispute',
            description='Test description'
        )
        
        # Test with regular user (should fail)
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('dispute-resolve', kwargs={'pk': dispute.id})
        data = {
            'resolution': 'Issue resolved in favor of buyer',
            'refund_amount': '500.00',
            'new_escrow_state': 'refunded'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Test with staff user (should succeed)
        self.client.force_authenticate(user=self.staff_user)
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'resolved')
        self.assertEqual(dispute.resolved_by, self.staff_user)

    def test_reservation_with_visit(self):
        # Create visit first
        slot = VisitSlot.objects.create(
            listing=self.listing,
            agent=self.seller,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1)
        )
        
        visit = Visit.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            slot=slot,
            status='completed'
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('reservation-list')
        data = {
            'listing': self.listing.id,
            'visit': str(visit.id),
            'reservation_type': 'rental',
            'start_at': (timezone.now() + timedelta(days=7)).isoformat(),
            'end_at': (timezone.now() + timedelta(days=14)).isoformat(),
            'amount': '1000.00'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        reservation = Reservation.objects.first()
        self.assertEqual(reservation.visit, visit)

    def test_permission_checks(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00')
        )
        
        # Other user should not see the reservation
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='testpass123'
        )
        
        self.client.force_authenticate(user=other_user)
        
        url = reverse('reservation-detail', kwargs={'pk': reservation.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Buyer should see the reservation
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reservation_analytics(self):
        # Create test reservations
        Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='completed'
        )
        
        Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('500.00'),
            escrow_state='paid'
        )
        
        self.client.force_authenticate(user=self.staff_user)
        
        url = reverse('reservation-analytics')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_reservations'], 2)
        self.assertEqual(response.data['total_value'], Decimal('1500.00'))

    def test_validation_errors(self):
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('reservation-list')
        
        # Test invalid date range
        data = {
            'listing': self.listing.id,
            'reservation_type': 'rental',
            'start_at': (timezone.now() + timedelta(days=7)).isoformat(),
            'end_at': (timezone.now() + timedelta(days=1)).isoformat(),  # End before start
            'amount': '1000.00'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', str(response.data))

    def test_dispute_validation(self):
        reservation = Reservation.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            amount=Decimal('1000.00'),
            escrow_state='initiated'  # Cannot dispute in this state
        )
        
        self.client.force_authenticate(user=self.buyer)
        
        url = reverse('dispute-list', kwargs={'reservation_id': reservation.id})
        data = {
            'dispute_type': 'property_condition',
            'title': 'Test Dispute',
            'description': 'Test description'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be disputed', str(response.data))


class ReservationPolicyServiceTests(TestCase):
    def test_get_default_policy(self):
        policy = ReservationPolicyService.get_default_policy()
        
        self.assertIn('cancellation', policy)
        self.assertIn('security_deposit', policy)
        self.assertEqual(policy['cancellation']['full_refund_days'], 7)

    def test_apply_policy_to_reservation(self):
        buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        
        seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        
        listing = Listing.objects.create(
            title='Test Listing',
            description='Test description',
            price=Decimal('1000.00'),
            listing_type='apartment',
            property_status='available',
            seller=seller
        )
        
        # Create policy
        policy_obj = ReservationPolicy.objects.create(
            name='Test Policy',
            security_deposit_percent=20
        )
        
        reservation = Reservation.objects.create(
            listing=listing,
            buyer=buyer,
            amount=Decimal('1000.00')
        )
        
        ReservationPolicyService.apply_policy_to_reservation(reservation, 'Test Policy')
        
        reservation.refresh_from_db()
        self.assertEqual(reservation.security_deposit, Decimal('200.00'))
        self.assertIn('cancellation', reservation.policy)