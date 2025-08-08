# listings/forms.py
from django import forms
from .models import Poi

class PoisForm(forms.ModelForm):
    class Meta:
        model = Poi
        fields = ["name", "latitude", "longitude"]

    def clean(self):
        data = super().clean()
        # You can validate ranges here if you want:
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is not None and not (-90 <= lat <= 90):
            self.add_error("latitude", "Latitude must be between -90 and 90.")
        if lon is not None and not (-180 <= lon <= 180):
            self.add_error("longitude", "Longitude must be between -180 and 180.")
        return data
