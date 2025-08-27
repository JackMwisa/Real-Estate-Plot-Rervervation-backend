from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from .models import (
    Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider,
    CurrencyExchangeRate, CommissionRule, SavingsGoal, SecurityAlert,
    WalletAnalytics, InvestmentPool, Investment
)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'owner_display', 'wallet_type', 'balance_cached', 'currency',
        'is_active', 'is_frozen', 'last_activity_at'
    ]
    list_filter = [
        'wallet_type', 'currency', 'is_active', 'is_frozen', 'requires_2fa'
    ]
    search_fields = [
        'owner_user__username', 'owner_user__email', 'owner_agency__agency_name'
    ]
    readonly_fields = [
        'id', 'calculated_balance', 'last_activity_at', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Ownership', {
            'fields': ('owner_user', 'owner_agency', 'wallet_type')
        }),
        ('Balance & Currency', {
            'fields': ('balance_cached', 'calculated_balance', 'currency')
        }),
        ('Security & Limits', {
            'fields': ('is_active', 'is_frozen', 'freeze_reason', 'requires_2fa', 'daily_limit', 'monthly_limit')
        }),
        ('Activity', {
            'fields': ('last_activity_at',)
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    def owner_display(self, obj):
        return obj.get_owner_display()
    owner_display.short_description = 'Owner'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'owner_user', 'owner_agency'
        )

    actions = ['refresh_balances', 'freeze_wallets', 'unfreeze_wallets']
    
    def refresh_balances(self, request, queryset):
        for wallet in queryset:
            wallet.refresh_balance()
        self.message_user(request, f'Refreshed {queryset.count()} wallet balances.')
    refresh_balances.short_description = 'Refresh cached balances'
    
    def freeze_wallets(self, request, queryset):
        updated = queryset.update(is_frozen=True, freeze_reason='Admin action')
        self.message_user(request, f'{updated} wallets frozen.')
    freeze_wallets.short_description = 'Freeze selected wallets'
    
    def unfreeze_wallets(self, request, queryset):
        updated = queryset.update(is_frozen=False, freeze_reason='')
        self.message_user(request, f'{updated} wallets unfrozen.')
    unfreeze_wallets.short_description = 'Unfreeze selected wallets'


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'wallet_owner', 'entry_type', 'amount', 'currency',
        'ref_type', 'balance_after', 'created_at'
    ]
    list_filter = [
        'entry_type', 'currency', 'ref_type', 'created_at'
    ]
    search_fields = [
        'wallet__owner_user__username', 'description', 'ref_id', 'txid'
    ]
    readonly_fields = [
        'id', 'balance_after', 'created_at'
    ]
    
    def wallet_owner(self, obj):
        return obj.wallet.get_owner_display()
    wallet_owner.short_description = 'Wallet Owner'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'wallet', 'wallet__owner_user', 'wallet__owner_agency', 'created_by'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'owner', 'payout_method', 'kyc_status', 'is_active',
        'is_default', 'created_at'
    ]
    list_filter = [
        'payout_method', 'kyc_status', 'is_active', 'is_default'
    ]
    search_fields = [
        'name', 'email', 'phone_number', 'owner__username'
    ]
    readonly_fields = [
        'id', 'kyc_verified_at', 'created_at', 'updated_at', 'can_receive_payouts'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'email', 'phone_number')
        }),
        ('KYC Status', {
            'fields': ('kyc_status', 'kyc_documents', 'kyc_verified_at')
        }),
        ('Payout Details', {
            'fields': ('payout_method', 'payout_details')
        }),
        ('Settings', {
            'fields': ('is_active', 'is_default', 'can_receive_payouts')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('owner')

    actions = ['verify_kyc', 'reject_kyc']
    
    def verify_kyc(self, request, queryset):
        updated = queryset.filter(kyc_status='pending').update(
            kyc_status='verified',
            kyc_verified_at=timezone.now()
        )
        self.message_user(request, f'{updated} beneficiaries verified.')
    verify_kyc.short_description = 'Verify KYC status'
    
    def reject_kyc(self, request, queryset):
        updated = queryset.filter(kyc_status='pending').update(kyc_status='rejected')
        self.message_user(request, f'{updated} beneficiaries rejected.')
    reject_kyc.short_description = 'Reject KYC status'


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'wallet_owner', 'beneficiary', 'amount', 'currency',
        'status', 'requires_approval', 'created_at'
    ]
    list_filter = [
        'status', 'currency', 'requires_approval', 'created_at'
    ]
    search_fields = [
        'wallet__owner_user__username', 'beneficiary__name', 'provider_ref'
    ]
    readonly_fields = [
        'id', 'net_amount', 'fee_amount', 'created_at', 'updated_at',
        'processed_at', 'completed_at', 'can_be_cancelled', 'is_completed'
    ]
    
    fieldsets = (
        ('Payout Details', {
            'fields': ('wallet', 'beneficiary', 'amount', 'currency', 'fee_amount', 'net_amount')
        }),
        ('Status', {
            'fields': ('status', 'provider_ref', 'failure_reason')
        }),
        ('Approval', {
            'fields': ('requires_approval', 'approved_by', 'approved_at')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'processed_at', 'completed_at'),
            'classes': ('collapse',)
        }),
        ('Status Properties', {
            'fields': ('can_be_cancelled', 'is_completed'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    def wallet_owner(self, obj):
        return obj.wallet.get_owner_display()
    wallet_owner.short_description = 'Wallet Owner'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'wallet', 'beneficiary', 'approved_by'
        )

    actions = ['approve_payouts', 'cancel_payouts']
    
    def approve_payouts(self, request, queryset):
        updated = queryset.filter(status='queued', requires_approval=True).update(
            approved_by=request.user,
            approved_at=timezone.now()
        )
        self.message_user(request, f'{updated} payouts approved.')
    approve_payouts.short_description = 'Approve selected payouts'
    
    def cancel_payouts(self, request, queryset):
        updated = queryset.filter(status__in=['queued', 'processing']).update(
            status='cancelled'
        )
        self.message_user(request, f'{updated} payouts cancelled.')
    cancel_payouts.short_description = 'Cancel selected payouts'


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'transaction_type', 'from_wallet_owner', 'to_wallet_owner',
        'amount', 'currency', 'status', 'created_at'
    ]
    list_filter = [
        'transaction_type', 'status', 'currency', 'created_at'
    ]
    search_fields = [
        'reference', 'description', 'external_ref'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'completed_at', 'is_transfer'
    ]
    
    def from_wallet_owner(self, obj):
        return obj.from_wallet.get_owner_display() if obj.from_wallet else '-'
    from_wallet_owner.short_description = 'From'
    
    def to_wallet_owner(self, obj):
        return obj.to_wallet.get_owner_display() if obj.to_wallet else '-'
    to_wallet_owner.short_description = 'To'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'from_wallet', 'to_wallet'
        )


@admin.register(CurrencyExchangeRate)
class CurrencyExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        'from_currency', 'to_currency', 'rate', 'provider', 'created_at', 'expires_at'
    ]
    list_filter = ['provider', 'created_at', 'expires_at']
    search_fields = ['from_currency', 'to_currency']
    readonly_fields = ['created_at', 'updated_at', 'is_expired']


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'rule_type', 'applies_to', 'percentage', 'fixed_amount',
        'is_active', 'priority'
    ]
    list_filter = ['rule_type', 'applies_to', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'wallet_owner', 'target_amount', 'current_amount', 'currency',
        'progress_percentage', 'status', 'target_date'
    ]
    list_filter = ['status', 'currency', 'auto_save_enabled']
    search_fields = ['name', 'wallet__owner_user__username']
    readonly_fields = ['progress_percentage', 'is_completed', 'created_at', 'updated_at']
    
    def wallet_owner(self, obj):
        return obj.wallet.get_owner_display()
    wallet_owner.short_description = 'Owner'


@admin.register(SecurityAlert)
class SecurityAlertAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'wallet_owner', 'alert_type', 'severity', 'title',
        'is_resolved', 'created_at'
    ]
    list_filter = ['alert_type', 'severity', 'is_resolved', 'created_at']
    search_fields = ['title', 'description', 'wallet__owner_user__username']
    readonly_fields = ['id', 'created_at']
    
    def wallet_owner(self, obj):
        return obj.wallet.get_owner_display()
    wallet_owner.short_description = 'Wallet Owner'


@admin.register(InvestmentPool)
class InvestmentPoolAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'target_amount', 'current_amount', 'currency',
        'funding_percentage', 'status', 'created_at'
    ]
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['funding_percentage', 'is_fully_funded', 'created_at', 'updated_at']


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = [
        'investor', 'pool', 'amount', 'currency', 'returns_earned',
        'roi_percentage', 'status', 'created_at'
    ]
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['investor__username', 'pool__name']
    readonly_fields = ['roi_percentage', 'created_at', 'updated_at']


@admin.register(PayoutProvider)
class PayoutProviderAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'min_payout_amount', 'max_payout_amount', 'is_active'
    ]
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(WalletAnalytics)
class WalletAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        'wallet_owner', 'date', 'opening_balance', 'closing_balance',
        'total_credits', 'total_debits', 'transaction_count'
    ]
    list_filter = ['date', 'wallet__currency']
    search_fields = ['wallet__owner_user__username']
    readonly_fields = ['created_at', 'updated_at']
    
    def wallet_owner(self, obj):
        return obj.wallet.get_owner_display()
    wallet_owner.short_description = 'Wallet Owner'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False