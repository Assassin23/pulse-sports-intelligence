"""
run_kafka_consumers management command.

Starts one or more Kafka consumer groups in long-running threads.
Each consumer group runs in its own daemon thread.

Usage:
    python manage.py run_kafka_consumers
    python manage.py run_kafka_consumers --consumers match score event
"""
import logging
import signal
import threading
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

CONSUMER_MAP = {
    "match": "sports_platform.kafka.consumers.match_consumers.MatchProcessorConsumer",
    "score": "sports_platform.kafka.consumers.match_consumers.ScoreProcessorConsumer",
    "event": "sports_platform.kafka.consumers.match_consumers.EventProcessorConsumer",
}


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class Command(BaseCommand):
    help = "Start Kafka consumer workers in background threads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--consumers",
            nargs="+",
            choices=list(CONSUMER_MAP.keys()),
            default=list(CONSUMER_MAP.keys()),
            help=f"Which consumers to start. Choices: {list(CONSUMER_MAP.keys())}",
        )

    def handle(self, *args, **options):
        chosen = options["consumers"]
        consumers = []
        threads = []

        self.stdout.write(f"Starting consumers: {chosen}")

        for name in chosen:
            cls = _import_class(CONSUMER_MAP[name])
            consumer = cls()
            consumers.append(consumer)
            t = threading.Thread(
                target=consumer.run,
                name=f"consumer-{name}",
                daemon=True,
            )
            threads.append(t)
            t.start()
            self.stdout.write(self.style.SUCCESS(f"  ✓ Started: {name} ({cls.__name__})"))

        # Graceful shutdown on SIGINT / SIGTERM
        def shutdown(signum, frame):
            self.stdout.write("\nShutting down consumers...")
            for c in consumers:
                c.stop()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # Keep main thread alive while daemon threads run
        try:
            while any(t.is_alive() for t in threads):
                time.sleep(1)
        except KeyboardInterrupt:
            for c in consumers:
                c.stop()

        self.stdout.write(self.style.SUCCESS("All consumers stopped."))
