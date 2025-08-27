from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers

from listings.models import Listing
from ..models import VerificationCase, VerificationDocument, VerificationOutcome, VerificationTemplate
from .serializers import (
    VerificationCaseSerializer, VerificationCaseCreateSerializer,
    VerificationDocumentSerializer, VerificationDecisionSerializer,
    VerificationTemplateSerializer, ListingVerificationStatusSerializer
)


class IsStaffOrOwner(permissions.BasePermission):
    """Allow staff to see all cases, users to see only their own"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.user == request.user


class VerificationCaseListView(generics.ListAPIView):
    """
    GET /api/verification/cases/
    List verification cases (staff: all cases, users: their own cases)
    """
    serializer_class = VerificationCaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'case_type', 'priority']
    search_fields = ['user__username', 'listing__title', 'submission_notes']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = VerificationCase.objects.select_related(
            'user', 'listing', 'assigned_to'
        ).prefetch_related('documents', 'outcome')
        
        if self.request.user.is_staff:
            return queryset
        else:
            return queryset.filter(user=self.request.user)


class VerificationCaseDetailView(generics.RetrieveAPIView):
    """
    GET /api/verification/cases/{id}/
    Get verification case details
    """
    serializer_class = VerificationCaseSerializer
    permission_classes = [IsStaffOrOwner]
    
    def get_queryset(self):
        return VerificationCase.objects.select_related(
            'user', 'listing', 'assigned_to'
        ).prefetch_related('documents', 'outcome')


class ListingVerifyView(generics.CreateAPIView):
    """
    POST /api/listings/{id}/verify/
    Submit listing for verification
    """
    serializer_class = VerificationCaseCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        listing_id = self.kwargs['listing_id']
        listing = get_object_or_404(Listing, id=listing_id, seller=self.request.user)
        
        # Check if there's already a pending case
        existing_case = VerificationCase.objects.filter(
            listing=listing,
            status__in=['submitted', 'under_review', 'needs_more_info']
        ).first()
        
        if existing_case:
            raise serializers.ValidationError("This listing already has a pending verification case")
        
        serializer.save(
            user=self.request.user,
            listing=listing,
            case_type='listing'
        )


class VerificationDocumentUploadView(generics.CreateAPIView):
    """
    POST /api/verification/cases/{case_id}/documents/
    Upload document for verification case
    """
    serializer_class = VerificationDocumentSerializer
    permission_classes = [IsStaffOrOwner]
    parser_classes = [MultiPartParser, FormParser]
    
    def perform_create(self, serializer):
        case_id = self.kwargs['case_id']
        case = get_object_or_404(VerificationCase, id=case_id)
        
        # Check permissions
        if not self.request.user.is_staff and case.user != self.request.user:
            raise permissions.PermissionDenied()
        
        serializer.save(verification_case=case)


class VerificationDocumentListView(generics.ListAPIView):
    """
    GET /api/verification/cases/{case_id}/documents/
    List documents for verification case
    """
    serializer_class = VerificationDocumentSerializer
    permission_classes = [IsStaffOrOwner]
    
    def get_queryset(self):
        case_id = self.kwargs['case_id']
        case = get_object_or_404(VerificationCase, id=case_id)
        
        # Check permissions
        if not self.request.user.is_staff and case.user != self.request.user:
            raise permissions.PermissionDenied()
        
        return VerificationDocument.objects.filter(verification_case=case)


class VerificationDecisionView(generics.UpdateAPIView):
    """
    PATCH /api/verification/cases/{id}/decision/
    Make verification decision (staff only)
    """
    serializer_class = VerificationDecisionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        if not self.request.user.is_staff:
            raise permissions.PermissionDenied("Only staff can make verification decisions")
        
        return get_object_or_404(VerificationCase, id=self.kwargs['pk'])
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        case = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        decision = serializer.validated_data['decision']
        reason = serializer.validated_data.get('reason', '')
        public_feedback = serializer.validated_data.get('public_feedback', '')
        valid_until = serializer.validated_data.get('valid_until')
        reviewer_notes = serializer.validated_data.get('reviewer_notes', '')
        
        # Update case status
        if decision == 'needs_more_info':
            case.status = 'needs_more_info'
            case.public_feedback = public_feedback
            case.reviewer_notes = reviewer_notes
            case.save(update_fields=['status', 'public_feedback', 'reviewer_notes', 'updated_at'])
        else:
            # Create outcome for verified/rejected
            case.status = decision
            case.reviewer_notes = reviewer_notes
            case.reviewed_at = timezone.now()
            case.save(update_fields=['status', 'reviewer_notes', 'reviewed_at', 'updated_at'])
            
            # Create or update outcome
            outcome, created = VerificationOutcome.objects.get_or_create(
                verification_case=case,
                defaults={
                    'outcome': decision,
                    'reason': reason,
                    'decided_by': request.user,
                    'valid_until': valid_until
                }
            )
            
            if not created:
                outcome.outcome = decision
                outcome.reason = reason
                outcome.decided_by = request.user
                outcome.valid_until = valid_until
                outcome.save()
        
        return Response({
            'status': 'success',
            'message': f'Verification case {decision}',
            'case_status': case.status
        })


class VerificationTemplateListView(generics.ListAPIView):
    """
    GET /api/verification/templates/
    List verification templates
    """
    serializer_class = VerificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = VerificationTemplate.objects.filter(is_active=True)
    filterset_fields = ['case_type']


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def listing_verification_status(request, listing_id):
    """
    GET /api/listings/{id}/verification-status/
    Get verification status for a listing
    """
    listing = get_object_or_404(Listing, id=listing_id)
    
    # Check if user can view this listing's verification status
    if not request.user.is_staff and listing.seller != request.user:
        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    # Get latest verification case
    latest_case = VerificationCase.objects.filter(
        listing=listing,
        case_type='listing'
    ).order_by('-created_at').first()
    
    # Determine verification status
    is_verified = False
    verification_status = 'not_submitted'
    verification_date = None
    verification_expires = None
    pending_case_id = None
    can_apply = True
    
    if latest_case:
        if latest_case.status in ['submitted', 'under_review', 'needs_more_info']:
            verification_status = latest_case.status
            pending_case_id = latest_case.id
            can_apply = False
        elif latest_case.status == 'verified':
            is_verified = True
            verification_status = 'verified'
            if hasattr(latest_case, 'outcome'):
                verification_date = latest_case.outcome.decided_at
                verification_expires = latest_case.outcome.valid_until
                is_verified = latest_case.outcome.is_active
        elif latest_case.status == 'rejected':
            verification_status = 'rejected'
            can_apply = True  # Can reapply after rejection
    
    data = {
        'is_verified': is_verified,
        'verification_status': verification_status,
        'verification_date': verification_date,
        'verification_expires': verification_expires,
        'pending_case_id': pending_case_id,
        'can_apply': can_apply
    }
    
    serializer = ListingVerificationStatusSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def agency_verification_status(request):
    """
    GET /api/verification/agency-status/
    Get agency verification status for current user
    """
    user = request.user
    
    # Check if user has an agency profile
    if not hasattr(user, 'profile') or not user.profile.agency_name:
        return Response({
            'has_agency': False,
            'is_verified': False,
            'verification_status': 'no_agency',
            'verification_date': None,
            'verification_expires': None,
            'pending_case_id': None,
            'can_apply': False
        })
    
    # Get latest agency verification case
    latest_case = VerificationCase.objects.filter(
        user=user,
        case_type='agency'
    ).order_by('-created_at').first()
    
    is_verified = False
    verification_status = 'not_submitted'
    verification_date = None
    verification_expires = None
    pending_case_id = None
    can_apply = True
    
    if latest_case:
        if latest_case.status in ['submitted', 'under_review', 'needs_more_info']:
            verification_status = latest_case.status
            pending_case_id = latest_case.id
            can_apply = False
        elif latest_case.status == 'verified':
            is_verified = True
            verification_status = 'verified'
            if hasattr(latest_case, 'outcome'):
                verification_date = latest_case.outcome.decided_at
                verification_expires = latest_case.outcome.valid_until
                is_verified = latest_case.outcome.is_active
        elif latest_case.status == 'rejected':
            verification_status = 'rejected'
            can_apply = True
    
    data = {
        'has_agency': True,
        'is_verified': is_verified,
        'verification_status': verification_status,
        'verification_date': verification_date,
        'verification_expires': verification_expires,
        'pending_case_id': pending_case_id,
        'can_apply': can_apply
    }
    
    serializer = ListingVerificationStatusSerializer(data)
    return Response(serializer.data)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_verification_status(request):
    """
    GET /api/verification/user-status/
    Get verification status for current user
    """
    user = request.user
    
    # Get latest user verification case
    latest_case = VerificationCase.objects.filter(
        user=user,
        case_type='user'
    ).order_by('-created_at').first()
    
    # Similar logic as listing verification status
    is_verified = False
    verification_status = 'not_submitted'
    verification_date = None
    verification_expires = None
    pending_case_id = None
    can_apply = True
    
    if latest_case:
        if latest_case.status in ['submitted', 'under_review', 'needs_more_info']:
            verification_status = latest_case.status
            pending_case_id = latest_case.id
            can_apply = False
        elif latest_case.status == 'verified':
            is_verified = True
            verification_status = 'verified'
            if hasattr(latest_case, 'outcome'):
                verification_date = latest_case.outcome.decided_at
                verification_expires = latest_case.outcome.valid_until
                is_verified = latest_case.outcome.is_active
        elif latest_case.status == 'rejected':
            verification_status = 'rejected'
            can_apply = True
    
    data = {
        'is_verified': is_verified,
        'verification_status': verification_status,
        'verification_date': verification_date,
        'verification_expires': verification_expires,
        'pending_case_id': pending_case_id,
        'can_apply': can_apply
    }
    
    serializer = ListingVerificationStatusSerializer(data)
    return Response(serializer.data)\
        
        
        
        
class UserVerifyView(generics.CreateAPIView):
    """
    POST /api/verification/user/verify/
    Start a USER verification case for the current user.
    """
    serializer_class = VerificationCaseCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user

        # prevent duplicate pending cases
        existing = VerificationCase.objects.filter(
            user=user,
            case_type='user',
            status__in=['submitted', 'under_review', 'needs_more_info'],
        ).first()
        if existing:
            raise serializers.ValidationError("You already have a pending user verification case.")

        serializer.save(
            user=user,
            case_type='user',
            listing=None,
        )


class AgencyVerifyView(generics.CreateAPIView):
    """
    POST /api/verification/agency/verify/
    Start an AGENCY verification case for the current user.
    """
    serializer_class = VerificationCaseCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user

        # OPTIONAL: check user has an agency profile. Keep as a soft guard.
        # If you have a concrete profile model/field, adjust this check.
        if not hasattr(user, 'profile') or not getattr(user.profile, 'agency_name', None):
            raise serializers.ValidationError("You must have an agency profile before verifying your agency.")

        # prevent duplicate pending cases
        existing = VerificationCase.objects.filter(
            user=user,
            case_type='agency',
            status__in=['submitted', 'under_review', 'needs_more_info'],
        ).first()
        if existing:
            raise serializers.ValidationError("You already have a pending agency verification case.")

        serializer.save(
            user=user,
            case_type='agency',
            listing=None,
        )
