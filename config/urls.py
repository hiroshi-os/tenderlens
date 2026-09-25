from django.contrib import admin
from django.urls import include, path

from tenders import views as tender_views

admin.site.site_header = "TenderLens"
admin.site.site_title = "TenderLens"
admin.site.index_title = "Public tender library"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", tender_views.healthz, name="healthz"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/signup/", tender_views.signup, name="signup"),
    path("", tender_views.tender_list, name="home"),
    path("tenders/<int:pk>/", tender_views.tender_detail, name="tender_detail"),
    path("dashboard/", tender_views.dashboard, name="dashboard"),
    path("dashboard/chart/<str:kind>.png", tender_views.chart, name="chart"),
    path("calendar/", tender_views.calendar_view, name="calendar"),
    path("awards/", tender_views.awards, name="awards"),
    path("", include("alerts.urls")),
]
