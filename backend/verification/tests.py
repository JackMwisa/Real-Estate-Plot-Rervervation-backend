from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal

from listings.models import Listing
from .models import VerificationCase, VerificationDocument, VerificationOutcome, VerificationTemplate

User = get_user_model()


class VerificationModelTests(TestCase):
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

    def test_verification_case_creation(self):
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing,
            submission_notes='Please verify my listing'
        )
        
        self.assertEqual(case.status, 'submitted')
        self.assertTrue(case.is_pending)
        self.assertFalse(case.is_completed)
        self.assertEqual(str(case), f"Listing Verification: {self.listing.title} (Submitted)")

    def test_verification_document_creation(self):
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing
        )
        
        # Create a simple test file
        test_file = SimpleUploadedFile(
            "test_document.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        document = VerificationDocument.objects.create(
            verification_case=case,
            document_type='title_deed',
            file=test_file,
            filename='test_document.pdf',
            file_size=len(b"file_content"),
            mime_type='application/pdf'
        )
        
        self.assertEqual(document.verification_case, case)
        self.assertEqual(document.document_type, 'title_deed')
        self.assertFalse(document.is_verified)

    def test_verification_outcome_creation(self):
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing
        )
        
        outcome = VerificationOutcome.objects.create(
            verification_case=case,
            outcome='verified',
            reason='All documents are valid',
            decided_by=self.staff_user
        )
        
        self.assertEqual(outcome.outcome, 'verified')
        self.assertTrue(outcome.is_active)
        self.assertEqual(outcome.decided_by, self.staff_user)

    def test_verification_template_creation(self):
        template = VerificationTemplate.objects.create(
            name='Standard Listing Verification',
            case_type='listing',
            description='Standard verification for property listings',
            required_documents=['title_deed', 'property_photos'],
            optional_documents=['floor_plans'],
            instructions='Please upload clear photos of your title deed'
        )
        
        self.assertEqual(template.case_type, 'listing')
        self.assertTrue(template.is_active)
        self.assertIn('title_deed', template.required_documents)


class VerificationAPITests(APITestCase):
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

    def test_listing_verification_submission(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('listing-verify', kwargs={'listing_id': self.listing.id})
        data = {
            'submission_notes': 'Please verify my listing',
            'priority': 'normal'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that verification case was created
        case = VerificationCase.objects.get(listing=self.listing)
        self.assertEqual(case.user, self.user)
        self.assertEqual(case.case_type, 'listing')
        self.assertEqual(case.status, 'submitted')

    def test_verification_case_list_user(self):
        # Create a verification case
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing
        )
        
        self.client.force_authenticate(user=self.user)
        
        url = reverse('verification-case-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], case.id)

    def test_verification_case_list_staff(self):
        # Create verification cases for different users
        case1 = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing
        )
        
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='pass123'
        )
        
        case2 = VerificationCase.objects.create(
            case_type='user',
            user=other_user
        )
        
        self.client.force_authenticate(user=self.staff_user)
        
        url = reverse('verification-case-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_verification_decision_staff_only(self):
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing,
            status='under_review'
        )
        
        # Test with regular user (should fail)
        self.client.force_authenticate(user=self.user)
        
        url = reverse('verification-decision', kwargs={'pk': case.id})
        data = {
            'decision': 'verified',
            'reason': 'All documents are valid'
        }
        
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Test with staff user (should succeed)
        self.client.force_authenticate(user=self.staff_user)
        
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that case was updated
        case.refresh_from_db()
        self.assertEqual(case.status, 'verified')
        
        # Check that outcome was created
        self.assertTrue(hasattr(case, 'outcome'))
        self.assertEqual(case.outcome.outcome, 'verified')

    def test_document_upload(self):
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing
        )
        
        self.client.force_authenticate(user=self.user)
        
        # Create a test file
        test_file = SimpleUploadedFile(
            "test_document.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        url = reverse('verification-document-upload', kwargs={'case_id': case.id})
        data = {
            'document_type': 'title_deed',
            'file': test_file,
            'description': 'Property title deed'
        }
        
        response = self.client.post(url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that document was created
        document = VerificationDocument.objects.get(verification_case=case)
        self.assertEqual(document.document_type, 'title_deed')

    def test_listing_verification_status(self):
        # Test without verification case
        self.client.force_authenticate(user=self.user)
        
        url = reverse('listing-verification-status', kwargs={'listing_id': self.listing.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_verified'])
        self.assertEqual(response.data['verification_status'], 'not_submitted')
        self.assertTrue(response.data['can_apply'])
        
        # Create a verified case
        case = VerificationCase.objects.create(
            case_type='listing',
            user=self.user,
            listing=self.listing,
            status='verified'
        )
        
        VerificationOutcome.objects.create(
            verification_case=case,
            outcome='verified',
            reason='Approved',
            decided_by=self.staff_user
        )
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_verified'])
        self.assertEqual(response.data['verification_status'], 'verified')

    def test_user_verification_status(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('user-verification-status')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_verified'])
        self.assertEqual(response.data['verification_status'], 'not_submitted')

    def test_verification_templates_list(self):
        template = VerificationTemplate.objects.create(
            name='Test Template',
            case_type='listing',
            description='Test template',
            required_documents=['title_deed'],
            is_active=True
        )
        
        self.client.force_authenticate(user=self.user)
        
        url = reverse('verification-template-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Test Template')

    def test_permission_checks(self):
        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='pass123'
        )
        
        case = VerificationCase.objects.create(
            case_type='listing',
            user=other_user,
            listing=self.listing
        )
        
        # User should not be able to access other user's case
        self.client.force_authenticate(user=self.user)
        
        url = reverse('verification-case-detail', kwargs={'pk': case.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Staff should be able to access any case
        self.client.force_authenticate(user=self.staff_user)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    def test_user_verification_submission(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('user-verify')
        data = {
            'submission_notes': 'Please verify my identity',
            'priority': 'normal'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that verification case was created
        case = VerificationCase.objects.get(user=self.user, case_type='user')
        self.assertEqual(case.status, 'submitted')

    def test_agency_verification_submission(self):
        # First set up agency profile
        self.user.profile.agency_name = 'Test Real Estate Agency'
        self.user.profile.save()
        
        self.client.force_authenticate(user=self.user)
        
        url = reverse('agency-verify')
        data = {
            'submission_notes': 'Please verify my agency',
            'priority': 'normal'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that verification case was created
        case = VerificationCase.objects.get(user=self.user, case_type='agency')
        self.assertEqual(case.status, 'submitted')

    def test_agency_verification_without_agency_profile(self):
        self.client.force_authenticate(user=self.user)
        
        url = reverse('agency-verify')
        data = {
            'submission_notes': 'Please verify my agency',
            'priority': 'normal'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agency profile', response.data['non_field_errors'][0])
    def test_user_verification_status(self):
        self.client.force_authenticate(user=self.user)
        
        # Test without verification case
        url = reverse('user-verification-status')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_verified'])
        self.assertEqual(response.data['verification_status'], 'not_submitted')
        
        # Create a verified case
        case = VerificationCase.objects.create(
            case_type='user',
            user=self.user,
            status='verified'
        )
        
        VerificationOutcome.objects.create(
            verification_case=case,
            outcome='verified',
            reason='Identity verified',
            decided_by=self.staff_user
        )
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_verified'])
        self.assertEqual(response.data['verification_status'], 'verified')
    def test_agency_verification_status(self):
        self.client.force_authenticate(user=self.user)
        
        # Test without agency profile
        url = reverse('agency-verification-status')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['has_agency'])
        self.assertEqual(response.data['verification_status'], 'no_agency')
        
        # Add agency profile
        self.user.profile.agency_name = 'Test Agency'
        self.user.profile.save()
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['has_agency'])
        self.assertEqual(response.data['verification_status'], 'not_submitted')