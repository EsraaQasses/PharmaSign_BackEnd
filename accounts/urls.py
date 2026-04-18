from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import AuthViewSet


app_name = 'accounts'

auth_viewset = AuthViewSet.as_view

urlpatterns = [
    path(
        'auth/pharmacist/register/',
        auth_viewset({'post': 'pharmacist_register'}),
        name='pharmacist_register',
    ),
    path('auth/login/', auth_viewset({'post': 'login'}), name='login'),
    path(
        'auth/patient/self-register/',
        auth_viewset({'post': 'patient_self_register'}),
        name='patient_self_register',
    ),
    path(
        'auth/patient/qr-login/',
        auth_viewset({'post': 'patient_qr_login'}),
        name='patient_qr_login',
    ),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', auth_viewset({'get': 'me'}), name='me'),
]
