# users/api/views.py
from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser
from users.models import Profile
from users.api.serializers import ProfileSerializer

class ProfileList(generics.ListAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer

class ProfileDetail(generics.RetrieveAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer
    lookup_field = "seller"          # ✅ lookup by the FK
    lookup_url_kwarg = "seller"      # ✅ match your <int:seller> in urls

class ProfileUpdate(generics.UpdateAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer
    lookup_field = "seller"          # ✅
    lookup_url_kwarg = "seller"      # ✅
    parser_classes = (MultiPartParser, FormParser)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True      # ✅ allow PATCH with partial data
        return super().update(request, *args, **kwargs)

class ProfileByUsernameDetail(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
    lookup_url_kwarg = "username"

    def get_queryset(self):
        return Profile.objects.select_related("seller")

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg)
        return self.get_queryset().get(seller__username=username)

class ProfileByUsernameUpdate(generics.UpdateAPIView):
    serializer_class = ProfileSerializer
    lookup_url_kwarg = "username"
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        return Profile.objects.select_related("seller")

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg)
        return self.get_queryset().get(seller__username=username)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)
