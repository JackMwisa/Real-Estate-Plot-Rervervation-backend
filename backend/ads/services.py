from typing import List, Dict, Any, Optional
from django.db.models import Q, F
from django.utils import timezone
from django.conf import settings
from decimal import Decimal

from .models import AdCampaign, AdImpression, AdClick


class AdRankingService:
    """Service for integrating ad boost scores into search ranking"""
    
    def __init__(self):
        self.enabled = getattr(settings, 'ADS_ENABLED', True)
        self.blend_weights = getattr(settings, 'ADS_RANK_BLEND_WEIGHTS', {
            'organic_score': 0.7,
            'boost_score': 0.3
        })
    
    def get_active_campaigns_for_listings(self, listing_ids: List[int]) -> Dict[int, float]:
        """Get boost scores for active campaigns targeting specific listings"""
        if not self.enabled or not listing_ids:
            return {}
        
        now = timezone.now()
        
        # Get active campaigns for these listings
        campaigns = AdCampaign.objects.filter(
            target_type='listing',
            target_id__in=listing_ids,
            status='active',
            start_at__lte=now,
            end_at__gte=now,
            spent_amount__lt=F('budget')
        ).values('target_id', 'boost_score')
        
        # Return mapping of listing_id -> boost_score
        boost_map = {}
        for campaign in campaigns:
            listing_id = campaign['target_id']
            boost_score = campaign['boost_score']
            
            # If multiple campaigns target the same listing, use the highest boost
            if listing_id not in boost_map or boost_score > boost_map[listing_id]:
                boost_map[listing_id] = boost_score
        
        return boost_map
    
    def blend_scores(self, organic_score: float, boost_score: float = 1.0) -> float:
        """Blend organic search score with ad boost score"""
        if not self.enabled:
            return organic_score
        
        organic_weight = self.blend_weights.get('organic_score', 0.7)
        boost_weight = self.blend_weights.get('boost_score', 0.3)
        
        # Normalize weights to sum to 1.0
        total_weight = organic_weight + boost_weight
        if total_weight > 0:
            organic_weight /= total_weight
            boost_weight /= total_weight
        
        return (organic_score * organic_weight) + (boost_score * boost_weight)
    
    def apply_ranking_boost(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply ad boost scores to search results"""
        if not self.enabled or not search_results:
            return search_results
        
        # Extract listing IDs
        listing_ids = [result.get('id') for result in search_results if result.get('id')]
        if not listing_ids:
            return search_results
        
        # Get boost scores
        boost_map = self.get_active_campaigns_for_listings(listing_ids)
        
        # Apply boost to results
        for result in search_results:
            listing_id = result.get('id')
            organic_score = result.get('_score', 1.0)  # Default score if not present
            boost_score = boost_map.get(listing_id, 1.0)
            
            # Calculate blended score
            blended_score = self.blend_scores(organic_score, boost_score)
            result['_score'] = blended_score
            result['_boosted'] = listing_id in boost_map
            result['_boost_score'] = boost_score
        
        # Re-sort by blended score
        search_results.sort(key=lambda x: x.get('_score', 0), reverse=True)
        
        return search_results


class AdBillingService:
    """Service for handling ad billing and cost calculations"""
    
    @staticmethod
    def calculate_impression_cost(campaign: AdCampaign) -> Decimal:
        """Calculate cost for a single impression"""
        if campaign.package.pricing_model == 'cpm':
            # CPM: cost per 1000 impressions
            return campaign.package.price / Decimal('1000')
        elif campaign.package.pricing_model == 'flat':
            # Flat rate: distribute cost over expected impressions
            # This is a simplified approach - in production you might want more sophisticated estimation
            expected_impressions = 10000  # Default estimate
            return campaign.budget / Decimal(str(expected_impressions))
        else:
            return Decimal('0.00')
    
    @staticmethod
    def calculate_click_cost(campaign: AdCampaign) -> Decimal:
        """Calculate cost for a single click"""
        if campaign.package.pricing_model == 'cpc':
            return campaign.package.price
        else:
            return Decimal('0.00')
    
    @staticmethod
    def update_campaign_spend(campaign: AdCampaign, cost: Decimal):
        """Update campaign spend and check budget limits"""
        AdCampaign.objects.filter(id=campaign.id).update(
            spent_amount=F('spent_amount') + cost
        )
        
        # Refresh campaign to check budget
        campaign.refresh_from_db()
        
        # Auto-pause if budget exceeded
        if campaign.spent_amount >= campaign.budget and campaign.status == 'active':
            campaign.status = 'completed'
            campaign.save(update_fields=['status', 'updated_at'])


class AdAnalyticsService:
    """Service for ad analytics and reporting"""
    
    @staticmethod
    def get_campaign_performance(campaign: AdCampaign, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive campaign performance metrics"""
        from datetime import timedelta
        from django.db.models import Sum, Count, Avg
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get impression metrics
        impression_stats = AdImpression.objects.filter(
            campaign=campaign,
            created_at__gte=start_date
        ).aggregate(
            total_impressions=Count('id'),
            total_impression_cost=Sum('cost')
        )
        
        # Get click metrics
        click_stats = AdClick.objects.filter(
            campaign=campaign,
            created_at__gte=start_date
        ).aggregate(
            total_clicks=Count('id'),
            total_click_cost=Sum('cost')
        )
        
        # Calculate derived metrics
        impressions = impression_stats['total_impressions'] or 0
        clicks = click_stats['total_clicks'] or 0
        impression_cost = impression_stats['total_impression_cost'] or Decimal('0.00')
        click_cost = click_stats['total_click_cost'] or Decimal('0.00')
        
        ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
        cpc = (click_cost / clicks) if clicks > 0 else Decimal('0.00')
        cpm = (impression_cost / impressions * 1000) if impressions > 0 else Decimal('0.00')
        
        return {
            'period_days': days,
            'impressions': impressions,
            'clicks': clicks,
            'ctr': round(ctr, 2),
            'cpc': cpc,
            'cpm': cpm,
            'total_cost': impression_cost + click_cost,
            'budget_utilization': float(campaign.spent_amount / campaign.budget * 100) if campaign.budget > 0 else 0.0
        }
    
    @staticmethod
    def get_top_performing_campaigns(limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing campaigns by CTR"""
        from django.db.models import Case, When, FloatField
        
        campaigns = AdCampaign.objects.filter(
            status__in=['active', 'completed'],
            impressions__gt=0
        ).annotate(
            ctr_calculated=Case(
                When(impressions__gt=0, then=F('clicks') * 100.0 / F('impressions')),
                default=0.0,
                output_field=FloatField()
            )
        ).order_by('-ctr_calculated')[:limit]
        
        results = []
        for campaign in campaigns:
            results.append({
                'id': str(campaign.id),
                'target_type': campaign.target_type,
                'target_id': campaign.target_id,
                'package_name': campaign.package.name,
                'impressions': campaign.impressions,
                'clicks': campaign.clicks,
                'ctr': campaign.ctr,
                'spent_amount': campaign.spent_amount,
                'status': campaign.status
            })
        
        return results