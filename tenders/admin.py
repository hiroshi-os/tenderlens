from django.contrib import admin

from tenders.models import Award, Buyer, CrawlCursor, CrawlRun, Tender


@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    list_display = ("organisation", "department", "ministry", "state")
    search_fields = ("organisation", "department", "ministry")


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ("source_key", "title", "source", "state", "deadline_at", "estimated_value_inr")
    list_filter = ("source", "status", "state")
    search_fields = ("title", "source_key", "reference_number", "description")
    raw_id_fields = ("buyer",)


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ("awardee_name", "source_key", "awarded_value_inr", "awarded_at")
    search_fields = ("awardee_name", "source_key")


@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "started_at", "finished_at")
    readonly_fields = ("stats", "marker_before", "marker_after", "error")


@admin.register(CrawlCursor)
class CrawlCursorAdmin(admin.ModelAdmin):
    list_display = ("source", "updated_at")
