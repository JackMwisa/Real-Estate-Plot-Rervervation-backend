from rest_framework import serializers
from users.models import Profile
from listings.models import Listing
from listings.api.serializers import ListingSerializer  # note the api path

class ProfileSerializer(serializers.ModelSerializer):
    seller_username = serializers.SerializerMethodField(read_only=True)
    seller_email = serializers.SerializerMethodField(read_only=True)
    seller_listings = serializers.SerializerMethodField(read_only=True)
    user_verification_status = serializers.SerializerMethodField(read_only=True)
    agency_verification_status = serializers.SerializerMethodField(read_only=True)



    def get_seller_username(self, obj):
        return obj.seller.username

    def get_seller_email(self, obj):
        return obj.seller.email

    def get_seller_listings(self, obj):
        qs = Listing.objects.filter(seller=obj.seller).order_by("-date_posted")
        return ListingSerializer(qs, many=True).data

    def get_user_verification_status(self, obj):
        """Get user verification status"""
        from verification.models import VerificationCase
        
        latest_case = VerificationCase.objects.filter(
            user=obj.seller,
            case_type='user'
        ).order_by('-created_at').first()
        
        if not latest_case:
            return {
                'is_verified': False,
                'status': 'not_submitted',
                'verified_at': None
            }
        
        if latest_case.status == 'verified':
            verified_at = None
            if hasattr(latest_case, 'outcome'):
                verified_at = latest_case.outcome.decided_at
            
            return {
                'is_verified': True,
                'status': 'verified',
                'verified_at': verified_at
            }
        elif latest_case.status in ['submitted', 'under_review', 'needs_more_info']:
            return {
                'is_verified': False,
                'status': latest_case.status,
                'verified_at': None
            }
        else:  # rejected
            return {
                'is_verified': False,
                'status': 'rejected',
                'verified_at': None
            }
    
    def get_agency_verification_status(self, obj):
        """Get agency verification status"""
        if not obj.agency_name:
            return {
                'has_agency': False,
                'is_verified': False,
                'status': 'no_agency',
                'verified_at': None
            }
        
        from verification.models import VerificationCase
        
        latest_case = VerificationCase.objects.filter(
            user=obj.seller,
            case_type='agency'
        ).order_by('-created_at').first()
        
        if not latest_case:
            return {
                'has_agency': True,
                'is_verified': False,
                'status': 'not_submitted',
                'verified_at': None
            }
        
        if latest_case.status == 'verified':
            verified_at = None
            if hasattr(latest_case, 'outcome'):
                verified_at = latest_case.outcome.decided_at
            
            return {
                'has_agency': True,
                'is_verified': True,
                'status': 'verified',
                'verified_at': verified_at
            }
        elif latest_case.status in ['submitted', 'under_review', 'needs_more_info']:
            return {
                'has_agency': True,
                'is_verified': False,
                'status': latest_case.status,
                'verified_at': None
            }
        else:  # rejected
            return {
                'has_agency': True,
                'is_verified': False,
                'status': 'rejected',
                'verified_at': None
            }
    class Meta:
        model = Profile
        fields = "__all__"
        read_only_fields = ("seller_username", "seller_email", "seller_listings", "user_verification_status", "agency_verification_status")