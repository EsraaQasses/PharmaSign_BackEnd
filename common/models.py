from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base class with created_at and updated_at timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
