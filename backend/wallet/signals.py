from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Wallet, LedgerEntry, Payout, WalletTransaction
from notifications.services import notify

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Create wallet when user is created"""
    if created:
        Wallet.objects.create(
            owner_user=instance,
            wallet_type='user',
            currency='USD'  # Default currency
        )


@receiver(post_save, sender=LedgerEntry)
def update_wallet_balance(sender, instance, created, **kwargs):
    """Update wallet cached balance when ledger entry is created"""
    if created:
        instance.wallet.refresh_balance()


@receiver(post_save, sender=Payout)
def payout_status_notification(sender, instance, created, **kwargs):
    """Send notification when payout status changes"""
    if created:
        # New payout created
        notify(
            user=instance.wallet.get_owner(),
            verb="wallet",
            message=f"Payout request for {instance.amount} {instance.currency} has been submitted and is being processed.",
            url=f"/wallet/payouts/{instance.id}",
            metadata={
                "payout_id": str(instance.id),
                "amount": str(instance.amount),
                "currency": instance.currency,
                "status": instance.status
            }
        )
    
    elif hasattr(instance, '_previous_status') and instance._previous_status != instance.status:
        owner = instance.wallet.get_owner()
        if not owner:
            return
            
        if instance.status == 'paid':
            notify(
                user=owner,
                verb="wallet",
                message=f"Your payout of {instance.amount} {instance.currency} has been successfully processed!",
                url=f"/wallet/payouts/{instance.id}",
                metadata={
                    "payout_id": str(instance.id),
                    "amount": str(instance.amount),
                    "currency": instance.currency,
                    "status": instance.status
                }
            )
        
        elif instance.status == 'failed':
            notify(
                user=owner,
                verb="wallet",
                message=f"Your payout of {instance.amount} {instance.currency} has failed. Please contact support.",
                url=f"/wallet/payouts/{instance.id}",
                metadata={
                    "payout_id": str(instance.id),
                    "amount": str(instance.amount),
                    "currency": instance.currency,
                    "status": instance.status,
                    "failure_reason": instance.failure_reason
                }
            )


@receiver(pre_save, sender=Payout)
def track_payout_status_change(sender, instance, **kwargs):
    """Track status changes for notifications"""
    if instance.pk:
        try:
            previous = Payout.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except Payout.DoesNotExist:
            instance._previous_status = None


@receiver(post_save, sender=WalletTransaction)
def wallet_transaction_notification(sender, instance, created, **kwargs):
    """Send notification for wallet transactions"""
    if not created or instance.status != 'completed':
        return
    
    # Notify sender
    if instance.from_wallet:
        from_owner = instance.from_wallet.get_owner()
        if from_owner:
            notify(
                user=from_owner,
                verb="wallet",
                message=f"Sent {instance.amount} {instance.currency} - {instance.description}",
                url="/wallet/",
                metadata={
                    "transaction_id": str(instance.id),
                    "amount": str(instance.amount),
                    "currency": instance.currency,
                    "type": "outgoing"
                }
            )
    
    # Notify receiver
    if instance.to_wallet:
        to_owner = instance.to_wallet.get_owner()
        if to_owner:
            notify(
                user=to_owner,
                verb="wallet",
                message=f"Received {instance.amount} {instance.currency} - {instance.description}",
                url="/wallet/",
                metadata={
                    "transaction_id": str(instance.id),
                    "amount": str(instance.amount),
                    "currency": instance.currency,
                    "type": "incoming"
                }
            )