from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Q
from decimal import Decimal

from ..models import Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider
from ..services import WalletService, PayoutService, LedgerService
from .serializers import (
    WalletSerializer, LedgerEntrySerializer, BeneficiarySerializer,
    PayoutSerializer, PayoutCreateSerializer, WalletTransactionSerializer,
    PayoutProviderSerializer, WalletBalanceSerializer, TransferFundsSerializer,
    LedgerInvariantSerializer
)


class IsWalletOwnerOrStaff(permissions.BasePermission):
    """Allow wallet owners and staff to access wallet data"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Check if user owns the wallet
        if hasattr(obj, 'wallet'):
            wallet = obj.wallet
        else:
            wallet = obj
        
        return (
            wallet.owner_user == request.user or
            (wallet.owner_agency and wallet.owner_agency.seller == request.user)
        )


class WalletDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/wallet/
    Get or update user's wallet
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Get or create user's wallet
        return WalletService.get_or_create_wallet(user=self.request.user)


class LedgerEntryListView(generics.ListAPIView):
    """
    GET /api/wallet/ledger/
    List user's ledger entries
    """
    serializer_class = LedgerEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['entry_type', 'ref_type', 'currency']
    search_fields = ['description', 'ref_id']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_staff:
            # Staff can see all entries
            return LedgerEntry.objects.select_related(
                'wallet', 'wallet__owner_user', 'wallet__owner_agency', 'created_by'
            )
        else:
            # Users see only their own entries
            try:
                wallet = user.wallet
                return wallet.ledger_entries.select_related('created_by')
            except Wallet.DoesNotExist:
                return LedgerEntry.objects.none()


class BeneficiaryListCreateView(generics.ListCreateAPIView):
    """
    GET /api/wallet/beneficiaries/ - List user's beneficiaries
    POST /api/wallet/beneficiaries/ - Create new beneficiary
    """
    serializer_class = BeneficiarySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['payout_method', 'kyc_status', 'is_active']
    ordering = ['-is_default', '-created_at']
    
    def get_queryset(self):
        return Beneficiary.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class BeneficiaryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/wallet/beneficiaries/{id}/
    """
    serializer_class = BeneficiarySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Beneficiary.objects.filter(owner=self.request.user)


class PayoutListCreateView(generics.ListCreateAPIView):
    """
    GET /api/wallet/payouts/ - List user's payouts
    POST /api/wallet/payouts/ - Create new payout
    """
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'currency', 'requires_approval']
    search_fields = ['beneficiary__name', 'provider_ref']
    ordering_fields = ['created_at', 'amount', 'completed_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PayoutCreateSerializer
        return PayoutSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_staff:
            return Payout.objects.select_related(
                'wallet', 'beneficiary', 'approved_by'
            )
        else:
            try:
                wallet = user.wallet
                return wallet.payouts.select_related('beneficiary', 'approved_by')
            except Wallet.DoesNotExist:
                return Payout.objects.none()
    
    def perform_create(self, serializer):
        user = self.request.user
        wallet = WalletService.get_or_create_wallet(user=user)
        
        # Use PayoutService to create payout with proper validation
        payout = PayoutService.create_payout(
            wallet=wallet,
            beneficiary=serializer.validated_data['beneficiary'],
            amount=serializer.validated_data['amount'],
            created_by=user
        )
        
        serializer.instance = payout


class PayoutDetailView(generics.RetrieveAPIView):
    """
    GET /api/wallet/payouts/{id}/
    """
    serializer_class = PayoutSerializer
    permission_classes = [IsWalletOwnerOrStaff]
    
    def get_queryset(self):
        return Payout.objects.select_related('wallet', 'beneficiary', 'approved_by')


class WalletTransactionListView(generics.ListAPIView):
    """
    GET /api/wallet/transactions/
    List wallet transactions
    """
    serializer_class = WalletTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['transaction_type', 'status', 'currency']
    search_fields = ['reference', 'description', 'external_ref']
    ordering_fields = ['created_at', 'amount', 'completed_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_staff:
            return WalletTransaction.objects.select_related(
                'from_wallet', 'to_wallet'
            )
        else:
            try:
                wallet = user.wallet
                return WalletTransaction.objects.filter(
                    Q(from_wallet=wallet) | Q(to_wallet=wallet)
                ).select_related('from_wallet', 'to_wallet')
            except Wallet.DoesNotExist:
                return WalletTransaction.objects.none()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_balance(request):
    """
    GET /api/wallet/balance/
    Get wallet balance summary
    """
    user = request.user
    
    try:
        wallet = user.wallet
    except Wallet.DoesNotExist:
        wallet = WalletService.get_or_create_wallet(user=user)
    
    # Calculate pending payouts
    pending_payouts = wallet.payouts.filter(
        status__in=['queued', 'processing']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    available_balance = wallet.balance_cached - pending_payouts
    
    data = {
        'balance': wallet.balance_cached,
        'currency': wallet.currency,
        'pending_payouts': pending_payouts,
        'available_balance': available_balance,
        'last_activity': wallet.last_activity_at
    }
    
    serializer = WalletBalanceSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_statement(request):
    """
    GET /api/wallet/statement/
    Get wallet statement with optional date range
    """
    user = request.user
    
    try:
        wallet = user.wallet
    except Wallet.DoesNotExist:
        return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Parse date parameters
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    limit = min(int(request.query_params.get('limit', 50)), 200)
    
    if start_date:
        from django.utils.dateparse import parse_datetime
        start_date = parse_datetime(start_date)
    
    if end_date:
        from django.utils.dateparse import parse_datetime
        end_date = parse_datetime(end_date)
    
    statement = LedgerService.get_wallet_statement(
        wallet=wallet,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    return Response(statement)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def transfer_funds(request):
    """
    POST /api/wallet/transfer/
    Transfer funds between wallets
    """
    serializer = TransferFundsSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    try:
        debit_entry, credit_entry = WalletService.transfer_funds(
            from_wallet=data['from_wallet'],
            to_wallet=data['to_wallet_id'],
            amount=data['amount'],
            description=data['description'],
            created_by=request.user
        )
        
        return Response({
            'status': 'success',
            'message': 'Transfer completed successfully',
            'transaction_id': str(debit_entry.txid),
            'debit_entry_id': str(debit_entry.id),
            'credit_entry_id': str(credit_entry.id)
        })
    
    except ValueError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_payout(request, pk):
    """
    POST /api/wallet/payouts/{id}/cancel/
    Cancel a payout
    """
    try:
        wallet = request.user.wallet
        payout = get_object_or_404(Payout, id=pk, wallet=wallet)
    except Wallet.DoesNotExist:
        return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if not payout.can_be_cancelled:
        return Response({'detail': 'Payout cannot be cancelled'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Cancel payout and refund amount
    payout.status = 'cancelled'
    payout.save(update_fields=['status', 'updated_at'])
    
    # Refund the amount back to wallet
    WalletService.credit_wallet(
        wallet=wallet,
        amount=payout.amount,
        ref_type='refund',
        ref_id=str(payout.id),
        description=f"Payout cancelled - refund for {payout.beneficiary.name}",
        created_by=request.user,
        metadata={'cancelled_payout_id': str(payout.id)}
    )
    
    return Response({
        'status': 'cancelled',
        'message': 'Payout cancelled and amount refunded to wallet'
    })


# Staff-only endpoints
@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def ledger_invariants(request):
    """
    GET /api/wallet/admin/invariants/
    Check ledger invariants (staff only)
    """
    wallet_id = request.query_params.get('wallet_id')
    
    if wallet_id:
        try:
            wallet = Wallet.objects.get(id=wallet_id)
            results = LedgerService.verify_ledger_invariants(wallet)
        except Wallet.DoesNotExist:
            return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        results = LedgerService.verify_ledger_invariants()
    
    serializer = LedgerInvariantSerializer(results)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def refresh_wallet_balances(request):
    """
    POST /api/wallet/admin/refresh-balances/
    Refresh cached balances for all wallets (staff only)
    """
    wallet_ids = request.data.get('wallet_ids', [])
    
    if wallet_ids:
        wallets = Wallet.objects.filter(id__in=wallet_ids)
    else:
        wallets = Wallet.objects.all()
    
    updated_count = 0
    for wallet in wallets:
        wallet.refresh_balance()
        updated_count += 1
    
    return Response({
        'status': 'success',
        'message': f'Refreshed {updated_count} wallet balances'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def approve_payout(request, pk):
    """
    POST /api/wallet/admin/payouts/{id}/approve/
    Approve a payout (staff only)
    """
    payout = get_object_or_404(Payout, id=pk)
    
    if not payout.requires_approval:
        return Response({'detail': 'Payout does not require approval'}, status=status.HTTP_400_BAD_REQUEST)
    
    if payout.status != 'queued':
        return Response({'detail': 'Payout is not in queued status'}, status=status.HTTP_400_BAD_REQUEST)
    
    payout.approved_by = request.user
    payout.approved_at = timezone.now()
    payout.save(update_fields=['approved_by', 'approved_at', 'updated_at'])
    
    return Response({
        'status': 'approved',
        'message': 'Payout approved successfully',
        'approved_at': payout.approved_at
    })


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def process_payout(request, pk):
    """
    POST /api/wallet/admin/payouts/{id}/process/
    Process a payout (staff only)
    """
    payout = get_object_or_404(Payout, id=pk)
    
    try:
        result = PayoutService.process_payout(payout)
        return Response(result)
    except ValueError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PayoutProviderListView(generics.ListAPIView):
    """
    GET /api/wallet/providers/
    List available payout providers
    """
    serializer_class = PayoutProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PayoutProvider.objects.filter(is_active=True)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_analytics(request):
    """
    GET /api/wallet/analytics/
    Get wallet analytics for user or global (staff)
    """
    user = request.user
    
    if user.is_staff:
        # Global analytics
        from django.db.models import Count, Avg
        
        analytics = Wallet.objects.aggregate(
            total_wallets=Count('id'),
            active_wallets=Count('id', filter=Q(is_active=True)),
            total_balance_usd=Sum('balance_cached', filter=Q(currency='USD')),
            total_balance_ugx=Sum('balance_cached', filter=Q(currency='UGX')),
            avg_balance=Avg('balance_cached')
        )
        
        # Payout statistics
        payout_stats = Payout.objects.aggregate(
            total_payouts=Count('id'),
            successful_payouts=Count('id', filter=Q(status='paid')),
            failed_payouts=Count('id', filter=Q(status='failed')),
            pending_payouts=Count('id', filter=Q(status__in=['queued', 'processing'])),
            total_payout_amount=Sum('amount')
        )
        
        analytics.update(payout_stats)
        
    else:
        # User analytics
        try:
            wallet = user.wallet
            
            # User's transaction summary
            from datetime import timedelta
            thirty_days_ago = timezone.now() - timedelta(days=30)
            
            recent_entries = wallet.ledger_entries.filter(created_at__gte=thirty_days_ago)
            
            analytics = {
                'wallet_balance': wallet.balance_cached,
                'currency': wallet.currency,
                'total_transactions_30d': recent_entries.count(),
                'credits_30d': recent_entries.filter(entry_type='credit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00'),
                'debits_30d': recent_entries.filter(entry_type='debit').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00'),
                'pending_payouts': wallet.payouts.filter(
                    status__in=['queued', 'processing']
                ).count(),
                'successful_payouts': wallet.payouts.filter(status='paid').count()
            }
            
        except Wallet.DoesNotExist:
            analytics = {
                'wallet_balance': Decimal('0.00'),
                'currency': 'USD',
                'total_transactions_30d': 0,
                'credits_30d': Decimal('0.00'),
                'debits_30d': Decimal('0.00'),
                'pending_payouts': 0,
                'successful_payouts': 0
            }
    
    return Response(analytics)