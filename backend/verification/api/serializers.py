from rest_framework import serializers
from django.contrib.auth import get_user_model
from ..models import VerificationCase, VerificationDocument, VerificationOutcome, VerificationTemplate

User = get_user_model()


class VerificationDocumentSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = VerificationDocument
        fields = [
            'id', 'document_type', 'file', 'filename', 'description',
            'file_size', 'file_size_mb', 'mime_type', 'is_verified',
            'verification_notes', 'uploaded_at', 'verified_at'
        ]
        read_only_fields = [
            'id', 'file_size', 'mime_type', 'is_verified', 
            'verification_notes', 'uploaded_at', 'verified_at'
        ]

    def create(self, validated_data):
        # Auto-populate filename and file metadata
        file_obj = validated_data['file']
        if not validated_data.get('filename'):
            validated_data['filename'] = file_obj.name
        
        validated_data['file_size'] = file_obj.size
        validated_data['mime_type'] = getattr(file_obj, 'content_type', '')
        
        return super().create(validated_data)


class VerificationOutcomeSerializer(serializers.ModelSerializer):
    decided_by_username = serializers.CharField(source='decided_by.username', read_only=True)
    is_active = serializers.ReadOnlyField()
    
    class Meta:
        model = VerificationOutcome
        fields = [
            'id', 'outcome', 'reason', 'decided_by_username', 'valid_until',
            'decided_at', 'confidence_score', 'is_active', 'metadata'
        ]
        read_only_fields = ['id', 'decided_at', 'decided_by_username', 'is_active']


class VerificationCaseSerializer(serializers.ModelSerializer):
    documents = VerificationDocumentSerializer(many=True, read_only=True)
    outcome = VerificationOutcomeSerializer(read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    is_pending = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    
    class Meta:
        model = VerificationCase
        fields = [
            'id', 'case_type', 'status', 'user', 'user_username', 
            'listing', 'listing_title', 'submission_notes', 'reviewer_notes',
            'public_feedback', 'assigned_to', 'assigned_to_username', 'priority',
            'created_at', 'updated_at', 'reviewed_at', 'metadata',
            'is_pending', 'is_completed', 'documents', 'outcome'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at', 'reviewed_at',
            'user_username', 'listing_title', 'assigned_to_username',
            'is_pending', 'is_completed'
        ]


class VerificationCaseCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating verification cases"""
    
    class Meta:
        model = VerificationCase
        fields = [
            'case_type', 'listing', 'submission_notes', 'priority', 'metadata'
        ]
    
    def validate(self, data):
        # Ensure listing belongs to the user (will be set in view)
        if data.get('case_type') == 'listing' and not data.get('listing'):
            raise serializers.ValidationError("Listing is required for listing verification")
        
        return data


class VerificationDecisionSerializer(serializers.Serializer):
    """Serializer for staff verification decisions"""
    
    decision = serializers.ChoiceField(choices=['verified', 'rejected', 'needs_more_info'])
    reason = serializers.CharField(required=False, allow_blank=True)
    public_feedback = serializers.CharField(required=False, allow_blank=True)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reviewer_notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if data['decision'] in ['rejected', 'needs_more_info'] and not data.get('reason'):
            raise serializers.ValidationError("Reason is required for rejection or when requesting more info")
        
        return data


class VerificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationTemplate
        fields = [
            'id', 'name', 'case_type', 'description', 'required_documents',
            'optional_documents', 'instructions', 'is_active', 'auto_approve_threshold'
        ]
        read_only_fields = ['id']


class ListingVerificationStatusSerializer(serializers.Serializer):
    """Serializer for listing verification status"""
    
    is_verified = serializers.BooleanField()
    verification_status = serializers.CharField()
    verification_date = serializers.DateTimeField(allow_null=True)
    verification_expires = serializers.DateTimeField(allow_null=True)
    pending_case_id = serializers.IntegerField(allow_null=True)
    can_apply = serializers.BooleanField()