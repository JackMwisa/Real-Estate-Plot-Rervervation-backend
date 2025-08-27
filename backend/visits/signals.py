# visits/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
import random
import string

from .models import Visit, VisitReminderTask


def _generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@receiver(post_save, sender=Visit)
def visit_post_save(sender, instance: Visit, created: bool, **kwargs):
    """
    When a visit is saved with status='confirmed', ensure it has a checkin_code and confirmed_at.
    Optionally schedule reminders (email) 24h and 1h before the slot start.
    """
    if instance.status != 'confirmed':
        return

    # If no checkin code yet, set it and confirmed_at without re-triggering signals
    updates = {}
    if not instance.checkin_code:
        updates['checkin_code'] = _generate_code()
    if instance.confirmed_at is None:
        updates['confirmed_at'] = timezone.now()

    if updates:
        updates['updated_at'] = timezone.now()
        Visit.objects.filter(pk=instance.pk).update(**updates)

    # Schedule reminders only for future visits
    start_at = instance.slot.start_at
    if start_at <= timezone.now():
        return

    desired_times = [start_at - timedelta(hours=24), start_at - timedelta(hours=1)]
    for when in desired_times:
        if when <= timezone.now():
            continue
        # De-dupe on (visit, type, scheduled_at)
        VisitReminderTask.objects.get_or_create(
            visit=instance,
            reminder_type='email',
            scheduled_at=when,
        )
