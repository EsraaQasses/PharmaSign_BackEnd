from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PharmacistProfileViewSet, PharmacyViewSet

router = DefaultRouter()
router.register('pharmacies', PharmacyViewSet, basename='pharmacy')

pharmacist_me = PharmacistProfileViewSet.as_view(
    {'get': 'retrieve', 'patch': 'partial_update'}
)

urlpatterns = [
    path('', include(router.urls)),
    path('pharmacists/me/', pharmacist_me, name='pharmacist-me'),
]
