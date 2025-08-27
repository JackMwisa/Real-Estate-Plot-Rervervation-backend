from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from .models import Wallet, LedgerEntry, Beneficiary, Payout, WalletTransaction, PayoutProvider


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'owner_display', 'wallet_type', 'balance_cached', 'currency',
        'is_active', 'last_activity_at'
    ]
    list_filter = ['wallet_type', 'currency', 'is_active', 'created_at']
    search_fields = [
        'owner_user__username', 'owner_agency__agency_name', 'owner_user__email'
    ]
    readonly_fields = [
        'id', 'balance_cached', 'calculated_balance', 'created_at', 
        'updated_at', 'last_activity_at'
    ]
    
    fieldsets = (
        ('Owner Information', {
            'fields': ('owner_user', 'owner_agency', 'wallet_type')
        }),
        ('Balance & Currency', {
            'fields': ('balance_cached', 'calculated_balance', 'currency')
        }),
        ('Limits & Controls', {
            'fields': ('is_active', 'daily_limit', 'monthly_limit')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_activity_at'),
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
    
    def calculated_balance(self, obj):
        calc_balance = obj.calculated_balance
        cached_balance = obj.balance_cached
        
        if calc_balance == cached_balance:
            return format_html(
                '<span style="color: green;">{} {}</span>',
                calc_balance, obj.currency
            )
        else:
            return format_html(
                '<span style="color: red;">{} {} (cached: {})</span>',
                calc_balance, obj.currency, cached_balance
            )
    calculated_balance.short_description = 'Calculated Balance'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'owner_user', 'owner_agency'
        )

    actions = ['refresh_balances', 'activate_wallets', 'deactivate_wallets']
    
    def refresh_balances(self, request, queryset):
        updated = 0
        for wallet in queryset:
            wallet.refresh_balance()
            updated += 1
        self.message_user(request, f'{updated} wallet balances refreshed.')
    refresh_balances.short_description = 'Refresh cached balances'
    
    def activate_wallets(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} wallets activated.')
    activate_wallets.short_description = 'Activate selected wallets'
    
    def deactivate_wallets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} wallets deactivated.')
    deactivate_wallets.short_description = 'Deactivate selected wallets'


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'wallet_owner', 'entry_type', 'amount', 'currency',
        'ref_type', 'description', 'created_at'
    ]
    list_filter = [
        'entry_type', 'ref_type', 'currency', 'created_at'
    ]
    search_fields = [
        'wallet__owner_user__username', 'description', 'ref_id', 'txid'
    ]
    readonly_fields = [
        'id', 'balance_after', 'created_at'
    ]
    
    fieldsets = (
        ('Entry Details', {
            'fields': ('wallet', 'entry_type', 'amount', 'currency', 'description')
        }),
        ('Reference', {
            'fields': ('ref_type', 'ref_id', 'txid')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'balance_after')
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
            'wallet', 'wallet__owner_user', 'wallet__owner_agency', 'created_by'
        )

    def has_add_permission(self, request):
        return False  # Ledger entries should be created via services
    
    def has_change_permission(self, request, obj=None):
        return False  # Immutable ledger


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'owner', 'payout_method', 'kyc_status', 'is_active', 
        'is_default', 'created_at'
    ]
    list_filter = ['payout_method', 'kyc_status', 'is_active', 'created_at']
    search_fields = ['name', 'email', 'phone_number', 'owner__username']
    readonly_fields = ['id', 'kyc_verified_at', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'email', 'phone_number')
        }),
        ('Payout Configuration', {
            'fields': ('payout_method', 'payout_details', 'is_active', 'is_default')
        }),
        ('KYC Status', {
            'fields': ('kyc_status', 'kyc_documents', 'kyc_verified_by', 'kyc_verified_at')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'owner', 'kyc_verified_by'
        )

    actions = ['verify_kyc', 'reject_kyc']
    
    def verify_kyc(self, request, queryset):
        updated = queryset.filter(kyc_status='pending').update(
            kyc_status='verified',
            kyc_verified_by=request.user,
            kyc_verified_at=timezone.now()
        )
        self.message_user(request, f'{updated} beneficiaries verified.')
    verify_kyc.short_description = 'Verify KYC for selected beneficiaries'
    
    def reject_kyc(self, request, queryset):
        updated = queryset.filter(kyc_status='pending').update(
            kyc_status='rejected'
        )
        self.message_user(request, f'{updated} beneficiaries rejected.')
    reject_kyc.short_description = 'Reject KYC for selected beneficiaries'


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'wallet_owner', 'beneficiary', 'amount', 'currency',
        'fee_amount', 'net_amount', 'status', 'created_at'
    ]
    list_filter = ['status', 'currency', 'requires_approval', 'created_at']
    search_fields = [
        'wallet__owner_user__username', 'beneficiary__name', 'provider_ref'
    ]
    readonly_fields = [
        'id', 'net_amount', 'created_at', 'updated_at', 
        'processed_at', 'completed_at'
    ]
    
    fieldsets = (
        ('Payout Details', {
            'fields': ('wallet', 'beneficiary', 'amount', 'currency', 'fee_amount', 'net_amount')
        }),
        ('Status & Processing', {
            'fields': ('status', 'provider_ref', 'failure_reason')
        }),
        ('Approval', {
            'fields': ('requires_approval', 'approved_by', 'approved_at')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'processed_at', 'completed_at'),
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
            'wallet', 'wallet__owner_user', 'wallet__owner_agency', 
            'beneficiary', 'approved_by'
        )

    actions = ['approve_payouts', 'cancel_payouts']
    
    def approve_payouts(self, request, queryset):
        updated = queryset.filter(
            status='queued', 
            requires_approval=True
        ).update(
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
    list_filter = ['transaction_type', 'status', 'currency', 'created_at']
    search_fields = [
        'reference', 'description', 'external_ref'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'completed_at'
    ]
    
    def from_wallet_owner(self, obj):
        return obj.from_wallet.get_owner_display() if obj.from_wallet else '-'
    from_wallet_owner.short_description = 'From'
    
    def to_wallet_owner(self, obj):
        return obj.to_wallet.get_owner_display() if obj.to_wallet else '-'
    to_wallet_owner.short_description = 'To'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'from_wallet', 'to_wallet', 'from_wallet__owner_user', 
            'to_wallet__owner_user', 'from_wallet__owner_agency', 
            'to_wallet__owner_agency'
        )


@admin.register(PayoutProvider)
class PayoutProviderAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'min_payout_amount', 'max_payout_amount', 'is_active'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'is_active')
        }),
        ('Capabilities', {
            'fields': ('supported_methods', 'supported_currencies')
        }),
        ('Limits', {
            'fields': ('min_payout_amount', 'max_payout_amount')
        }),
        ('Fee Structure', {
            'fields': ('fee_structure',)
        }),
        ('Configuration', {
            'fields': ('api_config',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )