from django.urls import path

from .views import AdminOrganizationMeView


urlpatterns = [
    path(
        "admin/organization/me/",
        AdminOrganizationMeView.as_view(),
        name="admin-organization-me",
    ),
]
