"""
Django management command to wait for the database to become available.
"""
import time
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Waits for the database to become available before continuing."

    def handle(self, *args, **options):
        self.stdout.write("Waiting for database...")
        db_conn = None
        attempts = 0
        max_attempts = 30
        while not db_conn and attempts < max_attempts:
            try:
                db_conn = connections["default"]
                db_conn.cursor()
            except OperationalError:
                attempts += 1
                self.stdout.write(f"Database unavailable, waiting 1 second... ({attempts}/{max_attempts})")
                time.sleep(1)

        if not db_conn or attempts >= max_attempts:
            self.stdout.write(self.style.ERROR("Database unavailable after 30 seconds!"))
            exit(1)

        self.stdout.write(self.style.SUCCESS("Database available!"))
