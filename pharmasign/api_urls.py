from django.urls import include, path

urlpatterns = [
    path('', include('accounts.urls')),
    path('', include('patients.urls')),
    path('', include('pharmacies.urls')),
    path('', include('prescriptions.urls')),
]
