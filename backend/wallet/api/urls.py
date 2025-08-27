from django.urls import path
from . import views

urlpatterns = [
    # Wallet management
    path('', views.WalletDetailView.as_view(), name='wallet-detail'),
    path('balance/', views.wallet_balance, name='wallet-balance'),
    path('statement/', views.wallet_statement, name='wallet-statement'),
    path('transfer/', views.transfer_funds, name='wallet-transfer'),
    path('analytics/', views.wallet_analytics, name='wallet-analytics'),
    
    # Ledger entries
    path('ledger/', views.LedgerEntryListView.as_view(), name='ledger-entry-list'),
    
    # Beneficiaries
    path('beneficiaries/', views.BeneficiaryListCreateView.as_view(), name='beneficiary-list'),
    path('beneficiaries/<uuid:pk>/', views.BeneficiaryDetailView.as_view(), name='beneficiary-detail'),
    
    # Payouts
    path('payouts/', views.PayoutListCreateView.as_view(), name='payout-list'),
    path('payouts/<uuid:pk>/', views.PayoutDetailView.as_view(), name='payout-detail'),
    path('payouts/<uuid:pk>/cancel/', views.cancel_payout, name='payout-cancel'),
    
    # Transactions
    path('transactions/', views.WalletTransactionListView.as_view(), name='wallet-transaction-list'),
    
    # Providers
    path('providers/', views.PayoutProviderListView.as_view(), name='payout-provider-list'),
    
    # Staff/admin endpoints
    path('admin/invariants/', views.ledger_invariants, name='ledger-invariants'),
    path('admin/refresh-balances/', views.refresh_wallet_balances, name='refresh-wallet-balances'),
    path('admin/payouts/<uuid:pk>/approve/', views.approve_payout, name='approve-payout'),
    path('admin/payouts/<uuid:pk>/process/', views.process_payout, name='process-payout'),
]