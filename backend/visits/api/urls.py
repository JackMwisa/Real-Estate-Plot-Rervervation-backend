from django.urls import path
from . import views

urlpatterns = [
    # Visit slots
    path('slots/', views.VisitSlotListCreateView.as_view(), name='visit-slot-list'),
    path('slots/<uuid:pk>/', views.VisitSlotDetailView.as_view(), name='visit-slot-detail'),
    
    # Visits
    path('', views.VisitListCreateView.as_view(), name='visit-list'),
    path('<uuid:pk>/', views.VisitDetailView.as_view(), name='visit-detail'),
    path('<uuid:pk>/confirm/', views.confirm_visit, name='visit-confirm'),
    path('<uuid:pk>/cancel/', views.cancel_visit, name='visit-cancel'),
    path('<uuid:pk>/checkin/', views.checkin_visit, name='visit-checkin'),
    path('<uuid:pk>/complete/', views.complete_visit, name='visit-complete'),
    path('<uuid:pk>/feedback/', views.submit_feedback, name='visit-feedback'),
    path('<uuid:pk>/no-show/', views.mark_no_show, name='visit-no-show'),
    
    # Utility endpoints
    path('upcoming/', views.my_upcoming_visits, name='my-upcoming-visits'),
]