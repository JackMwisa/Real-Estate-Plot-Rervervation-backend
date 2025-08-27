from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta

from .models import Visit, VisitReminderTask
from notifications.services import notify


@shared_task
def process_visit_reminders():
    """
    Process pending visit reminder notifications
    Run this task every 15 minutes
    """
    now = timezone.now()
    
    # Get pending reminders that should be sent
    pending_reminders = VisitReminderTask.objects.filter(
        is_sent=False,
        scheduled_at__lte=now
    ).select_related('visit', 'visit__buyer', 'visit__listing', 'visit__slot')
    
    sent_count = 0
    
    for reminder in pending_reminders:
        visit = reminder.visit
        
        # Skip if visit is cancelled or completed
        if visit.status in ['cancelled', 'completed', 'no_show']:
            reminder.is_sent = True
            reminder.sent_at = now
            reminder.save()
            continue
        
        # Send appropriate reminder notification
        if reminder.reminder_type == '24h_before':
            message = f"Reminder: You have a visit to {visit.listing.title} tomorrow at {visit.slot.start_at.strftime('%H:%M')}"
        elif reminder.reminder_type == '2h_before':
            message = f"Reminder: Your visit to {visit.listing.title} starts in 2 hours. Check-in code: {visit.checkin_code}"
        elif reminder.reminder_type == 'checkin_available':
            message = f"Check-in is now available for your visit to {visit.listing.title}. Use code: {visit.checkin_code}"
        else:
            continue
        
        # Send notification
        notify(
            user=visit.buyer,
            verb="visit_reminder",
            message=message,
            url=f"/visits/{visit.id}",
            metadata={
                "visit_id": str(visit.id),
                "reminder_type": reminder.reminder_type,
                "checkin_code": visit.checkin_code if visit.checkin_code else None
            }
        )
        
        # Mark as sent
        reminder.is_sent = True
        reminder.sent_at = now
        reminder.save()
        sent_count += 1
    
    return {
        'processed_reminders': sent_count,
        'processed_at': str(now)
    }


@shared_task
def mark_overdue_visits():
    """
    Mark confirmed visits as no-show if they're past due
    Run this task every hour
    """
    now = timezone.now()
    cutoff_time = now - timedelta(hours=1)  # 1 hour grace period
    
    # Find confirmed visits that are past their slot end time
    overdue_visits = Visit.objects.filter(
        status='confirmed',
        slot__end_at__lt=cutoff_time
    )
    
    updated_count = 0
    for visit in overdue_visits:
        visit.status = 'no_show'
        visit.save()
        
        # Notify agent
        notify(
            user=visit.slot.agent,
            verb="visit",
            message=f"Visit by {visit.buyer.username} to {visit.listing.title} marked as no-show",
            url=f"/visits/{visit.id}",
            metadata={
                "visit_id": str(visit.id),
                "status": "no_show"
            }
        )
        
        updated_count += 1
    
    return {
        'marked_no_show': updated_count,
        'processed_at': str(now)
    }


@shared_task
def cleanup_old_visit_data():
    """
    Clean up old visit data to manage database size
    Run this task weekly
    """
    # Delete old reminder tasks (older than 30 days)
    cutoff_date = timezone.now() - timedelta(days=30)
    
    deleted_reminders = VisitReminderTask.objects.filter(
        created_at__lt=cutoff_date,
        is_sent=True
    ).delete()
    
    return {
        'deleted_reminders': deleted_reminders[0] if deleted_reminders else 0,
        'cutoff_date': str(cutoff_date)
    }