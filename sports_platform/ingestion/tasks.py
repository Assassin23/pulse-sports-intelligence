"""
Celery tasks for sports data ingestion.

Tasks are scheduled via Celery Beat (DatabaseScheduler).
Each task creates a SportsIngestionWorker for its sport/provider pair.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# ── Upcoming fixtures ─────────────────────────────────────────────────────────

@shared_task(
    name="ingestion.poll_upcoming_fixtures",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=150,
)
def poll_upcoming_fixtures(self, sport: str, provider_name: str, days_ahead: int = 3):
    """
    Poll upcoming fixtures from a provider and publish match.discovered events.
    Scheduled: every 30 minutes.
    """
    try:
        from sports_platform.ingestion.worker import SportsIngestionWorker
        worker = SportsIngestionWorker(sport=sport, provider_name=provider_name)
        published = worker.ingest_upcoming(days_ahead=days_ahead)
        logger.info(
            "Upcoming fixture poll complete",
            extra={"sport": sport, "provider": provider_name, "published": published},
        )
        return {"published": published}
    except Exception as exc:
        logger.error(
            "Upcoming fixture task failed",
            extra={"sport": sport, "error": str(exc)},
        )
        raise self.retry(exc=exc)


@shared_task(
    name="ingestion.poll_live_matches",
    bind=True,
    max_retries=1,
    default_retry_delay=15,
    soft_time_limit=60,
    time_limit=90,
)
def poll_live_matches(self, sport: str, provider_name: str):
    """
    Poll live match scores and events, publish score.updated + match.event.
    Scheduled: every 30 seconds during match hours.
    """
    try:
        from sports_platform.ingestion.worker import SportsIngestionWorker
        worker = SportsIngestionWorker(sport=sport, provider_name=provider_name)
        published = worker.ingest_live()
        logger.info(
            "Live match poll complete",
            extra={"sport": sport, "provider": provider_name, "score_updates": published},
        )
        return {"score_updates": published}
    except Exception as exc:
        logger.error(
            "Live match poll task failed",
            extra={"sport": sport, "error": str(exc)},
        )
        raise self.retry(exc=exc)
