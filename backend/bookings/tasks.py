from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta

from .models import Reservation, DisputeCase
from .services import EscrowService
from notifications.services import notify


@shared_task
def process_reservation_transitions():
    """
    Process automatic reservation state transitions
    Run this task every hour
    """
    now = timezone.now()
    
    # Auto-complete reservations that have ended
    ending_reservations = Reservation.objects.filter(
        escrow_state='confirmed',
        end_at__lt=now
    )
    
    completed_count = 0
    for reservation in ending_reservations:
        try:
            reservation.escrow_state = 'completed'
            reservation.completed_at = now
            reservation.save(update_fields=['escrow_state', 'completed_at', 'updated_at'])
            completed_count += 1
        except Exception as e:
            # Log error but continue processing
            print(f"Error completing reservation {reservation.id}: {e}")
    
    # Cancel unpaid reservations after 24 hours
    expired_reservations = Reservation.objects.filter(
        escrow_state='initiated',
        created_at__lt=now - timedelta(hours=24)
    )
    
    cancelled_count = 0
    for reservation in expired_reservations:
        try:
            reservation.escrow_state = 'cancelled'
            reservation.cancellation_reason = 'Payment not received within 24 hours'
            reservation.cancelled_at = now
            reservation.save(update_fields=[
                'escrow_state', 'cancellation_reason', 'cancelled_at', 'updated_at'
            ])
            
            # Notify buyer
            notify(
                user=reservation.buyer,
                verb="booking",
                message=f"Your reservation for '{reservation.listing.title}' has been cancelled due to non-payment.",
                url=f"/bookings/{reservation.id}",
                metadata={
                    "reservation_id": str(reservation.id),
                    "reason": "payment_timeout"
                }
            )
            
            cancelled_count += 1
        except Exception as e:
            print(f"Error cancelling reservation {reservation.id}: {e}")
    
    return {
        'completed_reservations': completed_count,
        'cancelled_reservations': cancelled_count,
        'processed_at': str(now)
    }


@shared_task
def send_reservation_reminders():
    """
    Send reminders for upcoming reservations
    Run this task daily
    """
    now = timezone.now()
    
    # 24-hour reminders
    tomorrow = now + timedelta(days=1)
    upcoming_reservations = Reservation.objects.filter(
        escrow_state='confirmed',
        start_at__date=tomorrow.date(),
        metadata__reminder_24h_sent__isnull=True
    )
    
    reminders_sent = 0
    for reservation in upcoming_reservations:
        try:
            notify(
                user=reservation.buyer,
                verb="reminder",
                message=f"Reminder: Your {reservation.get_reservation_type_display().lower()} for '{reservation.listing.title}' starts tomorrow at {reservation.start_at.strftime('%I:%M %p')}.",
                url=f"/bookings/{reservation.id}",
                metadata={
                    "reservation_id": str(reservation.id),
                    "reminder_type": "24h"
                }
            )
            
            # Mark reminder as sent
            reservation.metadata['reminder_24h_sent'] = now.isoformat()
            reservation.save(update_fields=['metadata'])
            reminders_sent += 1
            
        except Exception as e:
            print(f"Error sending reminder for reservation {reservation.id}: {e}")
    
    return {
        'reminders_sent': reminders_sent,
        'processed_at': str(now)
    }


@shared_task
def escalate_old_disputes():
    """
    Escalate disputes that have been open too long
    Run this task daily
    """
    # Escalate disputes open for more than 3 days
    cutoff_date = timezone.now() - timedelta(days=3)
    
    old_disputes = DisputeCase.objects.filter(
        status__in=['open', 'investigating'],
        created_at__lt=cutoff_date,
        priority__in=['low', 'normal']
    )
    
    escalated_count = 0
    for dispute in old_disputes:
        try:
            from .services import DisputeService
            DisputeService.escalate_dispute(
                dispute, 
                reason="Auto-escalated due to extended resolution time"
            )
            escalated_count += 1
        except Exception as e:
            print(f"Error escalating dispute {dispute.id}: {e}")
    
    return {
        'escalated_disputes': escalated_count,
        'processed_at': str(timezone.now())
    }


@shared_task
def cleanup_old_reservations():
    """
    Clean up old completed/cancelled reservations
    Run this task weekly
    """
    # Archive reservations older than 1 year
    cutoff_date = timezone.now() - timedelta(days=365)
    
    old_reservations = Reservation.objects.filter(
        escrow_state__in=['completed', 'cancelled', 'refunded'],
        updated_at__lt=cutoff_date
    )
    
    # In a real system, you might move these to an archive table
    # For now, just mark them in metadata
    archived_count = 0
    for reservation in old_reservations:
        reservation.metadata['archived_at'] = timezone.now().isoformat()
        reservation.save(update_fields=['metadata'])
        archived_count += 1
    
    return {
        'archived_reservations': archived_count,
        'cutoff_date': str(cutoff_date)
    }