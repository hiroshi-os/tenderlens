from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class Buyer(models.Model):
    """A normalised contracting authority."""

    identity = models.CharField(max_length=700, unique=True)
    organisation = models.CharField(max_length=400)
    department = models.CharField(max_length=400, blank=True)
    ministry = models.CharField(max_length=400, blank=True)
    state = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["organisation", "department"]
        indexes = [
            models.Index(fields=["ministry"], name="buyer_ministry_idx"),
            models.Index(fields=["state"], name="buyer_state_idx"),
        ]

    def __str__(self) -> str:
        parts = [self.ministry, self.department, self.organisation]
        return " · ".join(part for part in parts if part) or self.organisation


class Tender(models.Model):
    class Source(models.TextChoices):
        CPPP = "cppp", "CPPP"
        GEM = "gem", "GeM"
        TNTENDERS = "tntenders", "Tamil Nadu"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        AWARDED = "awarded", "Awarded"
        UNKNOWN = "unknown", "Unknown"

    source = models.CharField(max_length=32, choices=Source.choices)
    source_key = models.CharField(max_length=200)
    feed = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=1000)
    description = models.TextField(blank=True)
    reference_number = models.CharField(max_length=300, blank=True)
    buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT, related_name="tenders")
    category = models.CharField(max_length=400, blank=True)
    state = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=300, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    estimated_value_inr = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    emd_inr = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    is_high_value = models.BooleanField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    opening_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    detail_url = models.URLField(max_length=2000, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    search_vector = SearchVectorField(null=True, editable=False)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline_at", "-published_at"]
        constraints = [
            models.UniqueConstraint(fields=["source", "source_key"], name="uniq_tender_source_key"),
            models.CheckConstraint(
                condition=models.Q(estimated_value_inr__gte=0)
                | models.Q(estimated_value_inr__isnull=True),
                name="tender_value_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(emd_inr__gte=0) | models.Q(emd_inr__isnull=True),
                name="tender_emd_nonnegative",
            ),
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="tender_search_gin"),
            models.Index(fields=["deadline_at"], name="tender_deadline_idx"),
            models.Index(fields=["published_at"], name="tender_published_idx"),
            models.Index(fields=["state"], name="tender_state_idx"),
            models.Index(fields=["category"], name="tender_category_idx"),
            models.Index(fields=["source", "published_at"], name="tender_source_published_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_key}: {self.title[:80]}"


class Award(models.Model):
    source = models.CharField(max_length=32)
    source_key = models.CharField(max_length=200)
    tender = models.ForeignKey(
        Tender, null=True, blank=True, on_delete=models.SET_NULL, related_name="awards"
    )
    buyer = models.ForeignKey(
        Buyer, null=True, blank=True, on_delete=models.SET_NULL, related_name="awards"
    )
    awardee_name = models.CharField(max_length=400)
    awardee_normalised = models.CharField(max_length=400)
    awarded_value_inr = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=100, blank=True)
    detail_url = models.URLField(max_length=2000, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "source_key"], name="uniq_award_source_key"),
            models.CheckConstraint(
                condition=models.Q(awarded_value_inr__gte=0)
                | models.Q(awarded_value_inr__isnull=True),
                name="award_value_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["awardee_normalised"], name="award_awardee_idx"),
            models.Index(fields=["awarded_at"], name="award_awarded_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.awardee_name} ({self.source_key})"


class CrawlCursor(models.Model):
    source = models.CharField(max_length=32, unique=True)
    marker = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.source


class CrawlRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    source = models.CharField(max_length=32)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    marker_before = models.JSONField(default=dict, blank=True)
    marker_after = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source", "-started_at"], name="crawlrun_source_started_idx")
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.status} {self.started_at:%Y-%m-%d %H:%M}"
