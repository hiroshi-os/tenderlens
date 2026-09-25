from django.urls import path

from alerts import views

urlpatterns = [
    path("searches/", views.search_list, name="searches"),
    path("searches/<int:pk>/delete/", views.search_delete, name="search_delete"),
    path("searches/<int:pk>/alert/", views.alert_from_search, name="alert_from_search"),
    path("alerts/", views.alert_list, name="alerts"),
    path("alerts/<int:pk>/delete/", views.alert_delete, name="alert_delete"),
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
]
