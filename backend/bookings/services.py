from typing import Dict, Any, Optional
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from .models import Reservation, DisputeCase, ReservationPolicy


class EscrowService:
    """Service for managing escrow state transitions"""
    
    @staticmethod
    def initiate_escrow(reservation: Reservation) -> Dict[str, Any]:
        """Initialize escrow for a reservation"""
        if reservation.escrow_state != 'initiated':
            raise ValueError("Reservation must be in initiated state")
        
        # Generate payment intent or redirect URL
        # This would integrate with your payments system
        return {
            'escrow_reference': reservation.escrow_reference,
            'amount': reservation.total_amount,
            'currency': reservation.currency,
            'payment_url': f"/payments/escrow/{reservation.id}/"
        }
    
    @staticmethod
    def process_payment_webhook(reservation_id: str, payment_data: Dict[str, Any]) -> bool:
        """Process payment webhook and update escrow state"""
        try:
            reservation = Reservation.objects.get(id=reservation_id)
        except Reservation.DoesNotExist:
            return False
        
        if payment_data.get('status') == 'successful':
            reservation.escrow_state = 'paid'
            reservation.metadata.update({
                'payment_confirmed_at': timezone.now().isoformat(),
                'payment_reference': payment_data.get('reference', '')
            })
            reservation.save(update_fields=['escrow_state', 'metadata', 'updated_at'])
            return True
        
        return False
    
    @staticmethod
    def release_escrow(reservation: Reservation, amount: Optional[Decimal] = None) -> Dict[str, Any]:
        """Release escrow funds to listing owner"""
        if reservation.escrow_state not in ['confirmed', 'completed']:
            raise ValueError("Cannot release escrow in current state")
        
        release_amount = amount or reservation.total_amount
        
        with transaction.atomic():
            reservation.escrow_state = 'released'
            reservation.metadata.update({
                'released_at': timezone.now().isoformat(),
                'released_amount': str(release_amount)
            })
            reservation.save(update_fields=['escrow_state', 'metadata', 'updated_at'])
        
        return {
            'status': 'released',
            'amount': release_amount,
            'recipient': reservation.listing.seller.username
        }
    
    @staticmethod
    def refund_escrow(reservation: Reservation, amount: Optional[Decimal] = None, reason: str = '') -> Dict[str, Any]:
        """Refund escrow funds to buyer"""
        if reservation.escrow_state not in ['paid', 'confirmed', 'disputed']:
            raise ValueError("Cannot refund escrow in current state")
        
        refund_amount = amount or reservation.calculate_refund_amount()
        
        with transaction.atomic():
            reservation.escrow_state = 'refunded'
            reservation.metadata.update({
                'refunded_at': timezone.now().isoformat(),
                'refund_amount': str(refund_amount),
                'refund_reason': reason
            })
            reservation.save(update_fields=['escrow_state', 'metadata', 'updated_at'])
        
        return {
            'status': 'refunded',
            'amount': refund_amount,
            'recipient': reservation.buyer.username
        }


class ReservationPolicyService:
    """Service for managing reservation policies"""
    
    @staticmethod
    def get_default_policy() -> Dict[str, Any]:
        """Get default reservation policy"""
        try:
            default_policy = ReservationPolicy.objects.filter(
                name__icontains='default',
                is_active=True
            ).first()
            
            if default_policy:
                return default_policy.to_policy_json()
        except Exception:
            pass
        
        # Fallback default policy
        return {
            'cancellation': {
                'full_refund_days': 7,
                'partial_refund_days': 3,
                'partial_refund_percent': 50,
            },
            'security_deposit': {
                'percent': 0,
                'fixed': 0.0,
            },
            'terms': 'Standard reservation terms apply.',
            'requires_verification': False,
        }
    
    @staticmethod
    def apply_policy_to_reservation(reservation: Reservation, policy_name: Optional[str] = None):
        """Apply a policy to a reservation"""
        if policy_name:
            try:
                policy_obj = ReservationPolicy.objects.get(name=policy_name, is_active=True)
                reservation.policy = policy_obj.to_policy_json()
                
                # Calculate and set security deposit
                security_deposit = policy_obj.calculate_security_deposit(reservation.amount)
                reservation.security_deposit = security_deposit
                
            except ReservationPolicy.DoesNotExist:
                reservation.policy = ReservationPolicyService.get_default_policy()
        else:
            reservation.policy = ReservationPolicyService.get_default_policy()
        
        reservation.save(update_fields=['policy', 'security_deposit', 'updated_at'])


class DisputeService:
    """Service for managing disputes"""
    
    @staticmethod
    def auto_assign_dispute(dispute: DisputeCase):
        """Auto-assign dispute to available staff member"""
        # Simple round-robin assignment
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        available_staff = User.objects.filter(
            is_staff=True,
            is_active=True
        ).order_by('assigned_disputes__created_at')
        
        if available_staff.exists():
            dispute.assigned_to = available_staff.first()
            dispute.status = 'investigating'
            dispute.save(update_fields=['assigned_to', 'status', 'updated_at'])
    
    @staticmethod
    def escalate_dispute(dispute: DisputeCase, reason: str = ''):
        """Escalate dispute to higher priority"""
        if dispute.priority != 'high':
            dispute.priority = 'high'
            dispute.metadata.update({
                'escalated_at': timezone.now().isoformat(),
                'escalation_reason': reason
            })
            dispute.save(update_fields=['priority', 'metadata', 'updated_at'])
    
    @staticmethod
    def get_dispute_statistics() -> Dict[str, Any]:
        """Get dispute resolution statistics"""
        from django.db.models import Count, Avg
        from datetime import timedelta
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        stats = DisputeCase.objects.filter(
            created_at__gte=thirty_days_ago
        ).aggregate(
            total_disputes=Count('id'),
            resolved_disputes=Count('id', filter=models.Q(status='resolved')),
            avg_resolution_time=Avg(
                models.F('resolved_at') - models.F('created_at'),
                filter=models.Q(status='resolved')
            )
        )
        
        # Dispute type distribution
        type_distribution = list(
            DisputeCase.objects.filter(created_at__gte=thirty_days_ago)
            .values('dispute_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        stats['type_distribution'] = type_distribution
        stats['resolution_rate'] = (
            (stats['resolved_disputes'] / stats['total_disputes'] * 100)
            if stats['total_disputes'] > 0 else 0
        )
        
        return stats