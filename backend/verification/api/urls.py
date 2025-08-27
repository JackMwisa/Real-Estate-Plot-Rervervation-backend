from django.urls import path
from . import views

urlpatterns = [
    # Verification cases
    path('cases/', views.VerificationCaseListView.as_view(), name='verification-case-list'),
    path('cases/<int:pk>/', views.VerificationCaseDetailView.as_view(), name='verification-case-detail'),
    path('cases/<int:pk>/decision/', views.VerificationDecisionView.as_view(), name='verification-decision'),
    
    # Verification submissions
    path('user/verify/', views.UserVerifyView.as_view(), name='user-verify'),
    path('agency/verify/', views.AgencyVerifyView.as_view(), name='agency-verify'),
    
    # Documents
    path('cases/<int:case_id>/documents/', views.VerificationDocumentListView.as_view(), name='verification-document-list'),
    path('cases/<int:case_id>/documents/upload/', views.VerificationDocumentUploadView.as_view(), name='verification-document-upload'),
    
    # Templates
    path('templates/', views.VerificationTemplateListView.as_view(), name='verification-template-list'),
    
    # Status endpoints
    path('user-status/', views.user_verification_status, name='user-verification-status'),
    path('agency-status/', views.agency_verification_status, name='agency-verification-status'),
]