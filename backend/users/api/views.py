from rest_framework import generics
from users.models import Profile
from users.api.serializers import ProfileSerializer

class ProfileList(generics.ListAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer

class ProfileDetail(generics.RetrieveAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer  # /api/users/profiles/<pk>/

class ProfileUpdate(generics.UpdateAPIView):
    queryset = Profile.objects.all().select_related("seller")
    serializer_class = ProfileSerializer  # /api/users/profiles/<pk>/update/

class ProfileByUsernameDetail(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer  # /api/users/profiles/u/<username>/
    lookup_url_kwarg = "username"

    def get_queryset(self):
        return Profile.objects.select_related("seller")

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg)
        return self.get_queryset().get(seller__username=username)

class ProfileByUsernameUpdate(generics.UpdateAPIView):
    serializer_class = ProfileSerializer  # /api/users/profiles/u/<username>/update/
    lookup_url_kwarg = "username"

    def get_queryset(self):
        return Profile.objects.select_related("seller")

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg)
        return self.get_queryset().get(seller__username=username)
