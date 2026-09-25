import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the local demo user when DEMO_PASSWORD is set."

    def handle(self, *args, **options):
        password = os.environ.get("DEMO_PASSWORD", "")
        username = os.environ.get("DEMO_USERNAME", "demo")
        if not password:
            self.stdout.write("DEMO_PASSWORD is unset; demo user was not created.")
            return
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": ""})
        user.set_password(password)
        user.save()
        self.stdout.write(f"demo user {'created' if created else 'updated'}: {username}")
        superuser_password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        superuser_name = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
        if (
            superuser_password
            and superuser_name
            and not User.objects.filter(username=superuser_name).exists()
        ):
            User.objects.create_superuser(
                superuser_name,
                os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@localhost"),
                superuser_password,
            )
            self.stdout.write(f"superuser created: {superuser_name}")
