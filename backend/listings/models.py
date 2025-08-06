from django.db import models
import timezone
from django.contrib.gis.db import models as gis_models
from django.conf import settings

# Create your models here.

class Listing(modles.Models):
    
    area_choices = [
        ('urban', 'Urban'),
        ('suburban', 'Suburban'),
        ('rural', 'Rural'),
    ]
    
    listing_type_choices = [
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('condo', 'Condo'),
        ('townhouse', 'Townhouse'),
        ('land', 'Land'),
    ]
    
    
    property_status_choices = [
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('pending', 'Pending'),
        ('rented', 'Rented'),
    ]
    
    rental_frequency_choices = [
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'),
        ('yearly', 'Yearly'),
    ]
    
    
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    area = models.CharField(max_length=100, blank=True, null=True, choices=area_choices)
    price = models.DecimalField(max_digits=50, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    borough = models.CharField(max_length=100, blank=True, null=True)
    listing_type = models.CharField(max_length=50, choices=listing_type_choices, default='apartment')
    property_status = models.CharField(max_length=50, choices=property_status_choices, default='available')
    rental_frequency = models.CharField(max_length=50, blank=True, null=True, choices=rental_frequency_choices)
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
    location = models.PointField(null=True, blank=True, help_text="Geographic location of the listing (latitude, longitude).", srid=4326)
    

    def __str__(self):
        return self.title