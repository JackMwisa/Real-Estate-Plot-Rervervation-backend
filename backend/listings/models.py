from django.db import models
from django.utils import timezone
# from django.contrib.gis.db import models as gis_models  # Uncomment if GDAL works

class Listing(models.Model):  # Fixed typo: modles -> models

    AREA_CHOICES = [
        ('urban', 'Urban'),
        ('suburban', 'Suburban'),
        ('rural', 'Rural'),
    ]

    LISTING_TYPE_CHOICES = [
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('condo', 'Condo'),
        ('townhouse', 'Townhouse'),
        ('land', 'Land'),
    ]

    PROPERTY_STATUS_CHOICES = [
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('pending', 'Pending'),
        ('rented', 'Rented'),
    ]

    RENTAL_FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'),
        ('yearly', 'Yearly'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    area = models.CharField(max_length=100, choices=AREA_CHOICES, null=True, blank=True)
    price = models.DecimalField(max_digits=50, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    borough = models.CharField(max_length=100, null=True, blank=True)
    listing_type = models.CharField(max_length=50, choices=LISTING_TYPE_CHOICES, default='apartment')
    property_status = models.CharField(max_length=50, choices=PROPERTY_STATUS_CHOICES, default='available')
    rental_frequency = models.CharField(max_length=50, choices=RENTAL_FREQUENCY_CHOICES, null=True, blank=True)
    
    furnished = models.BooleanField(default=False)
    pool = models.BooleanField(default=False)
    parking = models.BooleanField(default=False)
    cctv = models.BooleanField(default=False)
    garden = models.BooleanField(default=False)
    elevator = models.BooleanField(default=False)
    
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    area_size = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    date_available = models.DateField(null=True, blank=True)
    agent_name = models.CharField(max_length=100, blank=True, null=True)
    agent_phone = models.CharField(max_length=15, blank=True, null=True)
    date_posted = models.DateField(auto_now_add=True, default=timezone.now)
    
    # Use one of the two below depending on whether GDAL works
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # location = gis_models.PointField(null=True, blank=True, srid=4326)

    def __str__(self):
        return self.title
