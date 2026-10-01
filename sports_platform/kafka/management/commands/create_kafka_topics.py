"""
create_kafka_topics management command.

Creates all required Kafka topics if they don't already exist.
Idempotent — safe to run multiple times.

Usage:
    python manage.py create_kafka_topics
    python manage.py create_kafka_topics --partitions 6 --replication-factor 3
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from sports_platform.kafka.events import KafkaTopics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create all required Kafka topics (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--partitions", type=int, default=3, help="Number of partitions")
        parser.add_argument(
            "--replication-factor", type=int, default=1, help="Replication factor"
        )

    def handle(self, *args, **options):
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError

        num_partitions = options["partitions"]
        replication_factor = options["replication_factor"]
        bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS

        self.stdout.write(f"Connecting to Kafka: {bootstrap_servers}")
        try:
            admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
        except Exception as exc:
            raise SystemExit(f"Cannot connect to Kafka: {exc}")

        existing = set(admin.list_topics())
        topics = KafkaTopics.all_topics()

        to_create = []
        for topic_name in topics:
            if topic_name in existing:
                self.stdout.write(f"  ✓ Already exists: {topic_name}")
            else:
                to_create.append(
                    NewTopic(
                        name=topic_name,
                        num_partitions=num_partitions,
                        replication_factor=replication_factor,
                    )
                )

        if to_create:
            try:
                admin.create_topics(to_create)
                for t in to_create:
                    self.stdout.write(self.style.SUCCESS(f"  + Created: {t.name}"))
            except TopicAlreadyExistsError:
                self.stdout.write("  (Some topics already existed — no action needed)")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Error: {exc}"))
                raise

        admin.close()
        self.stdout.write(self.style.SUCCESS(f"\nDone. {len(topics)} topics verified."))
