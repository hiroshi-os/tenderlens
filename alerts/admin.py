from django.contrib import admin

from alerts.models import Alert, Notification, SavedSearch


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "keywords", "category", "state", "created_at")
    search_fields = ("name", "keywords", "user__username")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "channel", "is_active", "last_evaluated_at")
    list_filter = ("channel", "is_active")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "channel", "status", "created_at")
    list_filter = ("channel", "status")
    raw_id_fields = ("tender", "alert")
