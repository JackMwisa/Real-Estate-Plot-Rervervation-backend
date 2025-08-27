from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from listings.models import Listing

User = get_user_model()


class VerificationCase(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('needs_more_info', 'Needs More Info'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    CASE_TYPE_CHOICES = [
        ('listing', 'Listing Verification'),
        ('user', 'User Verification'),
        ('agency', 'Agency Verification'),
    ]

    # Core fields
    case_type = models.CharField(max_length=20, choices=CASE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    
    # Related objects
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='verification_cases'
    )
    listing = models.ForeignKey(
        Listing, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='verification_cases'
    )
    
    # Verification details
    submission_notes = models.TextField(blank=True, help_text="Notes from the applicant")
    reviewer_notes = models.TextField(blank=True, help_text="Internal notes from staff")
    public_feedback = models.TextField(blank=True, help_text="Feedback shown to applicant")
    
    # Staff assignment
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_verification_cases',
        limit_choices_to={'is_staff': True}
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Priority and metadata
    priority = models.CharField(
        max_length=10,
        choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High')],
        default='normal'
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'case_type']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        target = self.listing.title if self.listing else f"User {self.user.username}"
        return f"{self.get_case_type_display()}: {target} ({self.get_status_display()})"

    @property
    def is_pending(self):
        return self.status in ['submitted', 'under_review', 'needs_more_info']

    @property
    def is_completed(self):
        return self.status in ['verified', 'rejected']


class VerificationDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        # Listing documents
        ('title_deed', 'Title Deed'),
        ('land_certificate', 'Land Certificate'),
        ('building_permit', 'Building Permit'),
        ('occupancy_certificate', 'Occupancy Certificate'),
        ('property_photos', 'Property Photos'),
        ('floor_plans', 'Floor Plans'),
        
        # User/Agency documents
        ('national_id', 'National ID'),
        ('passport', 'Passport'),
        ('business_license', 'Business License'),
        ('tax_certificate', 'Tax Certificate'),
        ('professional_license', 'Professional License'),
        
        # Other
        ('other', 'Other Document'),
    ]

    verification_case = models.ForeignKey(
        VerificationCase,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='verification_documents/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # File metadata
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    
    # Verification status for this document
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} for {self.verification_case}"

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)


class VerificationOutcome(models.Model):
    OUTCOME_CHOICES = [
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
    ]

    verification_case = models.OneToOneField(
        VerificationCase,
        on_delete=models.CASCADE,
        related_name='outcome'
    )
    
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    reason = models.TextField(help_text="Reason for the decision")
    
    # Staff who made the decision
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='verification_decisions'
    )
    
    # Validity period (for verified outcomes)
    valid_until = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this verification expires (if applicable)"
    )
    
    # Timestamps
    decided_at = models.DateTimeField(auto_now_add=True)
    
    # Additional metadata
    confidence_score = models.FloatField(
        null=True, 
        blank=True,
        help_text="Confidence score (0.0-1.0) for automated decisions"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-decided_at']

    def __str__(self):
        return f"{self.get_outcome_display()} - {self.verification_case}"

    @property
    def is_active(self):
        if self.outcome != 'verified':
            return False
        if self.valid_until:
            from django.utils import timezone
            return timezone.now() < self.valid_until
        return True


class VerificationTemplate(models.Model):
    """Templates for different verification types with required documents"""
    
    name = models.CharField(max_length=100)
    case_type = models.CharField(max_length=20, choices=VerificationCase.CASE_TYPE_CHOICES)
    description = models.TextField()
    
    # Required document types for this template
    required_documents = models.JSONField(
        default=list,
        help_text="List of required document types"
    )
    
    # Optional document types
    optional_documents = models.JSONField(
        default=list,
        help_text="List of optional document types"
    )
    
    # Instructions for applicants
    instructions = models.TextField(blank=True)
    
    # Configuration
    is_active = models.BooleanField(default=True)
    auto_approve_threshold = models.FloatField(
        null=True,
        blank=True,
        help_text="Auto-approve if confidence score >= this value"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_case_type_display()})"