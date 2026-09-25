from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string

from alerts.models import Notification


class InAppBackend:
    """The notification row is the message. Nothing else is delivered."""

    def send(self, notification: Notification) -> None:
        notification.status = Notification.Status.SENT
        notification.error = ""


class EmailBackend:
    def send(self, notification: Notification) -> None:
        recipient = (notification.user.email or "").strip()
        if not recipient:
            notification.status = Notification.Status.FAILED
            notification.error = "User has no email address."
            return
        send_mail(
            notification.title,
            notification.body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        notification.status = Notification.Status.SENT
        notification.error = ""


def get_backend(channel: str):
    path = settings.NOTIFICATION_BACKENDS.get(channel)
    if not path:
        raise KeyError(f"No notification backend configured for {channel}")
    return import_string(path)()
