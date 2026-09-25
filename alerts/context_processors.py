from alerts.models import Notification


def unread_notifications(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"unread_notifications": 0}
    count = (
        Notification.objects.filter(user=request.user)
        .exclude(status=Notification.Status.READ)
        .count()
    )
    return {"unread_notifications": count}
