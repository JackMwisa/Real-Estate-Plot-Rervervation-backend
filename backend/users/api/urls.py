from django.urls import path
from . import views

urlpatterns = [
    path("", views.ProfileList.as_view(), name="profile-list"),
    path("<int:seller>/", views.ProfileDetail.as_view(), name="profile-detail"),
    path("<int:seller>/update/", views.ProfileUpdate.as_view(), name="profile-update"),
    
    # Alternative username-based endpoints
    path("username/<str:username>/", views.ProfileByUsernameDetail.as_view(), name="profile-by-username"),
    path("username/<str:username>/update/", views.ProfileByUsernameUpdate.as_view(), name="profile-by-username-update"),
]