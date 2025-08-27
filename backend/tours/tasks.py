from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Avg
from datetime import timedelta

from .models import TourAsset, TourAccessLog


@shared_task
def cleanup_old_access_logs():
    """
    Clean up old tour access logs to manage database size
    Run this task weekly
    """
    # Keep access logs for 90 days
    cutoff_date = timezone.now() - timedelta(days=90)
    
    deleted_logs = TourAccessLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    return {
        'deleted_logs': deleted_logs[0] if deleted_logs else 0,
        'cutoff_date': str(cutoff_date)
    }


@shared_task
def update_tour_analytics():
    """
    Update tour analytics and metrics
    Run this task daily
    """
    # Update access counts for tours that might be out of sync
    tours_updated = 0
    
    for tour in TourAsset.objects.all():
        actual_count = tour.access_logs.count()
        if tour.access_count != actual_count:
            tour.access_count = actual_count
            tour.save(update_fields=['access_count'])
            tours_updated += 1
    
    return {
        'tours_updated': tours_updated,
        'processed_at': str(timezone.now())
    }


@shared_task
def generate_tour_insights():
    """
    Generate insights about tour usage patterns
    Run this task weekly
    """
    # Get popular tour types
    popular_kinds = list(
        TourAsset.objects.values('kind')
        .annotate(
            total_tours=Count('id'),
            avg_access=Avg('access_count')
        )
        .order_by('-total_tours')
    )
    
    # Get popular providers
    popular_providers = list(
        TourAsset.objects.values('provider')
        .annotate(
            total_tours=Count('id'),
            avg_access=Avg('access_count')
        )
        .order_by('-total_tours')
    )
    
    # Get access patterns
    recent_logs = TourAccessLog.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    )
    
    access_by_method = list(
        recent_logs.values('access_method')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    access_by_device = list(
        recent_logs.exclude(device_type='')
        .values('device_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    return {
        'popular_kinds': popular_kinds,
        'popular_providers': popular_providers,
        'access_by_method': access_by_method,
        'access_by_device': access_by_device,
        'generated_at': str(timezone.now())
    }