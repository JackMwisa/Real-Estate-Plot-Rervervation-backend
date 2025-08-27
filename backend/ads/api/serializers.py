from rest_framework import serializers
from django.contrib.auth import get_user_model
from ..models import AdPackage, AdCampaign, AdImpression, AdClick, AdMetricsRollup

User = get_user_model()


class AdPackageSerializer(serializers.ModelSerializer):
    is_performance_based = serializers.ReadOnlyField()
    
    class Meta:
        model = AdPackage
        fields = [
            'id', 'name', 'sku', 'description', 'duration_days',
            'pricing_model', 'price', 'currency', 'geo_scope',
            'max_boost_score', 'featured_placement', 'priority_support',
            'analytics_access', 'is_active', 'is_performance_based'
        ]
        read_only_fields = ['id', 'is_performance_based']


class AdCampaignSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    target_object = serializers.SerializerMethodField()
    is_active = serializers.ReadOnlyField()
    ctr = serializers.ReadOnlyField()
    cost_per_click = serializers.ReadOnlyField()
    cost_per_impression = serializers.ReadOnlyField()
    can_serve_ad = serializers.ReadOnlyField()
    
    class Meta:
        model = AdCampaign
        fields = [
            'id', 'owner', 'owner_username', 'package', 'package_name',
            'target_type', 'target_id', 'target_object', 'start_at', 'end_at',
            'budget', 'currency', 'spent_amount', 'status', 'boost_score',
            'impressions', 'clicks', 'conversions', 'ctr', 'cost_per_click',
            'cost_per_impression', 'is_active', 'can_serve_ad', 'notes',
            'created_at', 'updated_at', 'approved_at'
        ]
        read_only_fields = [
            'id', 'owner', 'spent_amount', 'impressions', 'clicks', 
            'conversions', 'created_at', 'updated_at', 'approved_at'
        ]

    def get_target_object(self, obj):
        target = obj.get_target_object()
        if not target:
            return None
        
        if obj.target_type == 'listing':
            return {
                'id': target.id,
                'title': target.title,
                'price': str(target.price),
                'borough': target.borough
            }
        elif obj.target_type == 'agency':
            return {
                'id': target.id,
                'agency_name': target.agency_name,
                'username': target.seller.username
            }
        return None

    def validate(self, data):
        # Validate date range
        if data.get('start_at') and data.get('end_at'):
            if data['start_at'] >= data['end_at']:
                raise serializers.ValidationError("End date must be after start date")
        
        # Validate target exists
        target_type = data.get('target_type')
        target_id = data.get('target_id')
        
        if target_type and target_id:
            if target_type == 'listing':
                from listings.models import Listing
                if not Listing.objects.filter(id=target_id).exists():
                    raise serializers.ValidationError("Listing does not exist")
            elif target_type == 'agency':
                from users.models import Profile
                if not Profile.objects.filter(id=target_id).exists():
                    raise serializers.ValidationError("Agency profile does not exist")
        
        return data

    def validate_boost_score(self, value):
        # Ensure boost score doesn't exceed package limit
        if hasattr(self, 'initial_data'):
            package_id = self.initial_data.get('package')
            if package_id:
                try:
                    package = AdPackage.objects.get(id=package_id)
                    if value > package.max_boost_score:
                        raise serializers.ValidationError(
                            f"Boost score cannot exceed package limit of {package.max_boost_score}"
                        )
                except AdPackage.DoesNotExist:
                    pass
        return value


class AdCampaignCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating campaigns"""
    
    class Meta:
        model = AdCampaign
        fields = [
            'package', 'target_type', 'target_id', 'start_at', 'end_at',
            'budget', 'currency', 'boost_score', 'notes'
        ]

    def validate(self, data):
        # Validate user owns the target
        user = self.context['request'].user
        target_type = data.get('target_type')
        target_id = data.get('target_id')
        
        if target_type == 'listing':
            from listings.models import Listing
            try:
                listing = Listing.objects.get(id=target_id)
                if listing.seller != user:
                    raise serializers.ValidationError("You can only create campaigns for your own listings")
            except Listing.DoesNotExist:
                raise serializers.ValidationError("Listing does not exist")
        
        elif target_type == 'agency':
            from users.models import Profile
            try:
                profile = Profile.objects.get(id=target_id)
                if profile.seller != user:
                    raise serializers.ValidationError("You can only create campaigns for your own agency")
            except Profile.DoesNotExist:
                raise serializers.ValidationError("Agency profile does not exist")
        
        return super().validate(data)


class AdImpressionSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source='campaign.package.name', read_only=True)
    
    class Meta:
        model = AdImpression
        fields = [
            'id', 'campaign', 'campaign_name', 'user', 'session_id',
            'page_url', 'search_query', 'position', 'cost', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AdClickSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source='campaign.package.name', read_only=True)
    
    class Meta:
        model = AdClick
        fields = [
            'id', 'campaign', 'campaign_name', 'impression', 'user',
            'session_id', 'clicked_url', 'referrer_url', 'cost', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AdMetricsRollupSerializer(serializers.ModelSerializer):
    ctr = serializers.ReadOnlyField()
    cpc = serializers.ReadOnlyField()
    
    class Meta:
        model = AdMetricsRollup
        fields = [
            'campaign', 'date', 'impressions', 'clicks', 'conversions',
            'spend', 'ctr', 'cpc', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class CampaignMetricsSerializer(serializers.Serializer):
    """Serializer for campaign performance metrics"""
    
    total_impressions = serializers.IntegerField()
    total_clicks = serializers.IntegerField()
    total_conversions = serializers.IntegerField()
    total_spend = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_ctr = serializers.FloatField()
    average_cpc = serializers.DecimalField(max_digits=8, decimal_places=4)
    daily_metrics = AdMetricsRollupSerializer(many=True)


class AdTrackingSerializer(serializers.Serializer):
    """Serializer for tracking ad events"""
    
    campaign_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=['impression', 'click'])
    page_url = serializers.URLField(required=False)
    search_query = serializers.CharField(max_length=500, required=False)
    position = serializers.IntegerField(required=False)
    clicked_url = serializers.URLField(required=False)
    referrer_url = serializers.URLField(required=False)