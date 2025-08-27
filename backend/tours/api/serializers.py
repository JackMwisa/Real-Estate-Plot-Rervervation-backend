from rest_framework import serializers
from django.contrib.auth import get_user_model
from ..models import TourAsset, TourAccessLog, TourTemplate

User = get_user_model()


class TourAssetSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    is_embeddable = serializers.ReadOnlyField()
    embed_url_generated = serializers.SerializerMethodField()
    access_allowed = serializers.SerializerMethodField()
    
    class Meta:
        model = TourAsset
        fields = [
            'id', 'listing', 'listing_title', 'title', 'description',
            'kind', 'provider', 'url', 'embed_url', 'embed_url_generated',
            'thumbnail_url', 'is_gated', 'access_requirements', 'access_count',
            'last_accessed_at', 'duration_seconds', 'file_size_mb', 'metadata',
            'is_active', 'is_embeddable', 'access_allowed', 'created_at',
            'updated_at', 'created_by', 'created_by_username'
        ]
        read_only_fields = [
            'id', 'access_count', 'last_accessed_at', 'created_at', 
            'updated_at', 'created_by'
        ]

    def get_embed_url_generated(self, obj):
        return obj.get_embed_url()

    def get_access_allowed(self, obj):
        request = self.context.get('request')
        if not request:
            return True
        
        allowed, reason = obj.check_access_requirements(request.user)
        return {
            'allowed': allowed,
            'reason': reason
        }

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class TourAssetCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating tour assets"""
    
    class Meta:
        model = TourAsset
        fields = [
            'listing', 'title', 'description', 'kind', 'provider',
            'url', 'embed_url', 'thumbnail_url', 'is_gated',
            'access_requirements', 'duration_seconds', 'file_size_mb',
            'metadata'
        ]

    def validate_listing(self, value):
        """Ensure user can add tours to this listing"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not request.user.is_staff and value.seller != request.user:
                raise serializers.ValidationError(
                    "You can only add tours to your own listings"
                )
        return value


class TourAccessLogSerializer(serializers.ModelSerializer):
    tour_title = serializers.CharField(source='tour_asset.title', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = TourAccessLog
        fields = [
            'id', 'tour_asset', 'tour_title', 'user', 'user_username',
            'session_id', 'access_method', 'referrer_url', 'duration_seconds',
            'device_type', 'browser', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class TourTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TourTemplate
        fields = [
            'id', 'name', 'description', 'provider', 'kind',
            'default_gated', 'default_requirements', 'url_pattern',
            'embed_pattern', 'is_active'
        ]
        read_only_fields = ['id']


class TourAccessRequestSerializer(serializers.Serializer):
    """Serializer for requesting tour access"""
    
    access_method = serializers.ChoiceField(
        choices=['direct', 'embed', 'api'],
        default='direct'
    )
    referrer_url = serializers.URLField(required=False, allow_blank=True)
    device_type = serializers.CharField(max_length=20, required=False, allow_blank=True)
    browser = serializers.CharField(max_length=50, required=False, allow_blank=True)


class TourSummarySerializer(serializers.Serializer):
    """Serializer for tour summary in listing details"""
    
    total_tours = serializers.IntegerField()
    has_3d_tours = serializers.BooleanField()
    has_video_tours = serializers.BooleanField()
    has_360_photos = serializers.BooleanField()
    gated_count = serializers.IntegerField()
    public_tours = TourAssetSerializer(many=True)