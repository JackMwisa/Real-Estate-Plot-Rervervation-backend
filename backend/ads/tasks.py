from celery import shared_task
from django.utils import timezone
from django.db.models import Sum, Count, F
from datetime import timedelta, date
from decimal import Decimal

from .models import AdCampaign, AdImpression, AdClick, AdMetricsRollup
from .services import AdBillingService


@shared_task
def rollup_daily_ad_metrics():
    """
    Daily task to rollup ad metrics for performance and billing
    Run this task nightly via Celery Beat
    """
    yesterday = timezone.now().date() - timedelta(days=1)
    
    # Get all campaigns that had activity yesterday
    active_campaigns = AdCampaign.objects.filter(
        Q(impression_events__created_at__date=yesterday) |
        Q(click_events__created_at__date=yesterday)
    ).distinct()
    
    rollups_created = 0
    rollups_updated = 0
    
    for campaign in active_campaigns:
        # Get impression metrics for yesterday
        impression_stats = AdImpression.objects.filter(
            campaign=campaign,
            created_at__date=yesterday
        ).aggregate(
            count=Count('id'),
            cost=Sum('cost')
        )
        
        # Get click metrics for yesterday
        click_stats = AdClick.objects.filter(
            campaign=campaign,
            created_at__date=yesterday
        ).aggregate(
            count=Count('id'),
            cost=Sum('cost')
        )
        
        impressions = impression_stats['count'] or 0
        clicks = click_stats['count'] or 0
        impression_cost = impression_stats['cost'] or Decimal('0.00')
        click_cost = click_stats['cost'] or Decimal('0.00')
        total_spend = impression_cost + click_cost
        
        # Create or update rollup record
        rollup, created = AdMetricsRollup.objects.update_or_create(
            campaign=campaign,
            date=yesterday,
            defaults={
                'impressions': impressions,
                'clicks': clicks,
                'spend': total_spend,
                'conversions': 0  # TODO: Implement conversion tracking
            }
        )
        
        if created:
            rollups_created += 1
        else:
            rollups_updated += 1
    
    return {
        'date': str(yesterday),
        'campaigns_processed': len(active_campaigns),
        'rollups_created': rollups_created,
        'rollups_updated': rollups_updated
    }


@shared_task
def update_campaign_statuses():
    """
    Task to update campaign statuses based on dates and budget
    Run this task hourly
    """
    now = timezone.now()
    
    # Mark expired campaigns as completed
    expired_campaigns = AdCampaign.objects.filter(
        status='active',
        end_at__lt=now
    ).update(status='completed')
    
    # Mark budget-exhausted campaigns as completed
    budget_exhausted = AdCampaign.objects.filter(
        status='active',
        spent_amount__gte=F('budget')
    ).update(status='completed')
    
    # Activate campaigns that should start now
    starting_campaigns = AdCampaign.objects.filter(
        status='pending',
        start_at__lte=now,
        end_at__gt=now,
        approved_at__isnull=False
    ).update(status='active')
    
    return {
        'expired_campaigns': expired_campaigns,
        'budget_exhausted_campaigns': budget_exhausted,
        'activated_campaigns': starting_campaigns,
        'processed_at': str(now)
    }


@shared_task
def process_ad_billing():
    """
    Task to process ad billing and update campaign spend
    Run this task every few hours
    """
    # Get impressions without billing processed
    unbilled_impressions = AdImpression.objects.filter(cost=Decimal('0.00'))
    
    impressions_processed = 0
    for impression in unbilled_impressions:
        cost = AdBillingService.calculate_impression_cost(impression.campaign)
        impression.cost = cost
        impression.save(update_fields=['cost'])
        
        # Update campaign spend
        AdBillingService.update_campaign_spend(impression.campaign, cost)
        impressions_processed += 1
    
    # Get clicks without billing processed
    unbilled_clicks = AdClick.objects.filter(cost=Decimal('0.00'))
    
    clicks_processed = 0
    for click in unbilled_clicks:
        cost = AdBillingService.calculate_click_cost(click.campaign)
        click.cost = cost
        click.save(update_fields=['cost'])
        
        # Update campaign spend
        AdBillingService.update_campaign_spend(click.campaign, cost)
        clicks_processed += 1
    
    return {
        'impressions_processed': impressions_processed,
        'clicks_processed': clicks_processed,
        'processed_at': str(timezone.now())
    }


@shared_task
def cleanup_old_ad_events():
    """
    Task to cleanup old ad impression and click events
    Run this task weekly to manage database size
    """
    # Keep events for 90 days
    cutoff_date = timezone.now() - timedelta(days=90)
    
    # Delete old impressions
    deleted_impressions = AdImpression.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    # Delete old clicks
    deleted_clicks = AdClick.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    return {
        'deleted_impressions': deleted_impressions[0] if deleted_impressions else 0,
        'deleted_clicks': deleted_clicks[0] if deleted_clicks else 0,
        'cutoff_date': str(cutoff_date)
    }