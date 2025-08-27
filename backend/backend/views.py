from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta

from listings.models import Listing
from users.models import Profile
from notifications.models import Notification

User = get_user_model()


def api_root(request):
    """API root endpoint with system overview"""
    
    # Get system statistics
    stats = {
        'total_users': User.objects.count(),
        'total_listings': Listing.objects.count(),
        'available_listings': Listing.objects.filter(property_status='available').count(),
        'total_profiles': Profile.objects.count(),
        'recent_notifications': Notification.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
    }
    
    # API endpoints
    endpoints = {
        'authentication': {
            'register': '/api-auth-djoser/users/',
            'login': '/api-auth-djoser/auth/token/login/',
            'logout': '/api-auth-djoser/auth/token/logout/',
        },
        'core_features': {
            'listings': '/api/listings/',
            'profiles': '/api/profiles/',
            'payments': '/api/payments/',
            'notifications': '/api/notifications/',
        },
        'advanced_features': {
            'search': '/api/search/',
            'tours': '/api/tours/',
            'visits': '/api/visits/',
            'bookings': '/api/bookings/',
            'wallet': '/api/wallet/',
            'ads': '/api/ads/',
            'verification': '/api/verification/',
        },
        'admin': {
            'admin_panel': '/admin/',
            'api_docs': '/api/',
        }
    }
    
    # Feature flags
    features = {
        'bookings_enabled': getattr(settings, 'BOOKINGS_ENABLED', True),
        'wallet_enabled': getattr(settings, 'WALLET_ENABLED', True),
        'ads_enabled': getattr(settings, 'ADS_ENABLED', True),
        'tours_enabled': getattr(settings, 'TOURS_ENABLED', True),
        'verification_enabled': getattr(settings, 'VERIFICATION_ENABLED', True),
    }
    
    # System info
    system_info = {
        'version': '1.0.0',
        'environment': 'development' if settings.DEBUG else 'production',
        'debug_mode': settings.DEBUG,
        'timezone': str(settings.TIME_ZONE),
        'database': settings.DATABASES['default']['ENGINE'].split('.')[-1],
    }
    
    if request.content_type == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'message': 'Welcome to Real Estate Platform API',
            'status': 'operational',
            'timestamp': timezone.now().isoformat(),
            'statistics': stats,
            'endpoints': endpoints,
            'features': features,
            'system': system_info,
        })
    
    # Render HTML template
    context = {
        'stats': stats,
        'endpoints': endpoints,
        'features': features,
        'system_info': system_info,
    }
    
    return render(request, 'backend/api_root.html', context)


def health_check(request):
    """Health check endpoint for monitoring"""
    
    try:
        # Test database connection
        user_count = User.objects.count()
        
        # Test basic functionality
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'database': 'connected',
            'user_count': user_count,
            'uptime': 'operational',
        }
        
        return JsonResponse(health_status)
    
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'timestamp': timezone.now().isoformat(),
            'error': str(e),
        }, status=503)