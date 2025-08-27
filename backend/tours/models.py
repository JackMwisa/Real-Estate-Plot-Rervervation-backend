from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import URLValidator
from django.utils import timezone
import uuid

User = get_user_model()


class TourAsset(models.Model):
    """Virtual tour assets linked to listings"""
    
    KIND_CHOICES = [
        ('3d', '3D Tour'),
        ('video', 'Video Tour'),
        ('360', '360° Photos'),
        ('vr', 'VR Experience'),
    ]
    
    PROVIDER_CHOICES = [
        ('matterport', 'Matterport'),
        ('zillow', 'Zillow 3D Home'),
        ('cupix', 'Cupix'),
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('custom', 'Custom/Self-hosted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        'listings.Listing', 
        on_delete=models.CASCADE, 
        related_name='tour_assets'
    )
    
    # Tour details
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='3d')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='custom')
    
    # URLs and access
    url = models.URLField(validators=[URLValidator()])
    embed_url = models.URLField(blank=True, help_text="Embeddable URL if different from main URL")
    thumbnail_url = models.URLField(blank=True)
    
    # Access control
    is_gated = models.BooleanField(
        default=False, 
        help_text="Require special access to view this tour"
    )
    access_requirements = models.JSONField(
        default=dict,
        blank=True,
        help_text="Requirements for gated access (verified_user, paid_visit, etc.)"
    )
    
    # Analytics
    access_count = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    duration_seconds = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Tour duration in seconds"
    )
    file_size_mb = models.FloatField(
        null=True, 
        blank=True,
        help_text="File size in MB for hosted content"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional provider-specific metadata"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_tours'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['listing', 'is_active']),
            models.Index(fields=['kind', 'provider']),
            models.Index(fields=['is_gated']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} - {self.listing.title}"

    def increment_access_count(self):
        """Increment access count and update last accessed time"""
        self.access_count += 1
        self.last_accessed_at = timezone.now()
        self.save(update_fields=['access_count', 'last_accessed_at'])

    @property
    def is_embeddable(self):
        """Check if tour can be embedded"""
        return bool(self.embed_url or self.provider in ['matterport', 'youtube', 'vimeo'])

    def get_embed_url(self):
        """Get the appropriate embed URL"""
        if self.embed_url:
            return self.embed_url
        
        # Generate embed URLs for known providers
        if self.provider == 'youtube' and 'watch?v=' in self.url:
            video_id = self.url.split('watch?v=')[1].split('&')[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif self.provider == 'vimeo' and 'vimeo.com/' in self.url:
            video_id = self.url.split('vimeo.com/')[1].split('/')[0]
            return f"https://player.vimeo.com/video/{video_id}"
        
        return self.url

    def check_access_requirements(self, user):
        """Check if user meets access requirements for gated content"""
        if not self.is_gated:
            return True, None
        
        if not user or not user.is_authenticated:
            return False, "Authentication required"
        
        requirements = self.access_requirements
        
        # Check verified user requirement
        if requirements.get('verified_user', False):
            if not hasattr(user, 'profile'):
                return False, "User profile required"
            
            # Check if user has verified status
            from verification.models import VerificationCase
            verified_case = VerificationCase.objects.filter(
                user=user,
                case_type='user',
                status='verified'
            ).first()
            
            if not verified_case:
                return False, "User verification required"
        
        # Check paid visit requirement
        if requirements.get('paid_visit', False):
            from visits.models import Visit
            paid_visit = Visit.objects.filter(
                buyer=user,
                listing=self.listing,
                status__in=['completed', 'checked_in'],
                fee_paid=True
            ).first()
            
            if not paid_visit:
                return False, "Paid visit required"
        
        # Check confirmed visit requirement
        if requirements.get('confirmed_visit', False):
            from visits.models import Visit
            confirmed_visit = Visit.objects.filter(
                buyer=user,
                listing=self.listing,
                status__in=['confirmed', 'checked_in', 'completed']
            ).first()
            
            if not confirmed_visit:
                return False, "Confirmed visit required"
        
        return True, None


class TourAccessLog(models.Model):
    """Log tour access for analytics and billing"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tour_asset = models.ForeignKey(
        TourAsset, 
        on_delete=models.CASCADE, 
        related_name='access_logs'
    )
    
    # User context
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    session_id = models.CharField(max_length=128, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Access details
    access_method = models.CharField(
        max_length=20,
        choices=[
            ('direct', 'Direct Link'),
            ('embed', 'Embedded View'),
            ('api', 'API Access'),
        ],
        default='direct'
    )
    referrer_url = models.URLField(blank=True)
    duration_seconds = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Time spent viewing tour"
    )
    
    # Metadata
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tour_asset', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]

    def __str__(self):
        return f"Access to {self.tour_asset} at {self.created_at}"


class TourTemplate(models.Model):
    """Templates for common tour configurations"""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    provider = models.CharField(max_length=20, choices=TourAsset.PROVIDER_CHOICES)
    kind = models.CharField(max_length=10, choices=TourAsset.KIND_CHOICES)
    
    # Default settings
    default_gated = models.BooleanField(default=False)
    default_requirements = models.JSONField(default=dict, blank=True)
    
    # Template configuration
    url_pattern = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL pattern with placeholders like {tour_id}"
    )
    embed_pattern = models.CharField(
        max_length=500,
        blank=True,
        help_text="Embed URL pattern with placeholders"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()})"