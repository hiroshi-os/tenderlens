from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from tenders.models import Tender


class FilterSet(models.Model):
    """Shared keyword and facet filters. Concrete tables subclass this."""

    keywords = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=400, blank=True)
    state = models.CharField(max_length=100, blank=True)
    ministry = models.CharField(max_length=400, blank=True)
    min_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    closing_before = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        if not any([self.keywords, self.category, self.state, self.ministry, self.closing_before]):
            if self.min_value is None and self.max_value is None:
                raise ValidationError(
                    "Set at least one keyword, category, place, buyer, or date filter."
                )
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValidationError("Minimum value cannot exceed maximum value.")

    def as_filters(self) -> dict:
        return {
            "q": self.keywords,
            "category": self.category,
            "state": self.state,
            "ministry": self.ministry,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "closing_before": self.closing_before,
        }


class SavedSearch(FilterSet):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches"
    )
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_saved_search_name"),
        ]

    def __str__(self) -> str:
        return self.name


class Alert(FilterSet):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In app"
        EMAIL = "email", "Email"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alerts"
    )
    saved_search = models.ForeignKey(
        SavedSearch, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    name = models.CharField(max_length=120)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.IN_APP)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.saved_search_id:
            if self.saved_search.user_id != self.user_id:
                raise ValidationError("A saved search can only feed alerts for its owner.")
            return
        super().clean()

    def effective_filters(self) -> dict:
        if self.saved_search_id:
            return self.saved_search.as_filters()
        return self.as_filters()


class Notification(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        READ = "read", "Read"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="notifications")
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["alert", "tender"], name="uniq_alert_tender_notification"
            ),
        ]
        indexes = [models.Index(fields=["user", "status"], name="notification_user_status_idx")]

    def __str__(self) -> str:
        return self.title
