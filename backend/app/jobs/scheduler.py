"""In-app scheduler: runs the daily job once a day at DAILY_JOB_HOUR (server local time).

Good for a single server or a demo. In production with several workers, turn it off
(SCHEDULER_ENABLED=false) and run `python -m app.jobs.daily` from cron / Task Scheduler instead.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.config import get_settings
from app.jobs import daily

log = logging.getLogger(__name__)


def seconds_until(hour: int, now: datetime | None = None) -> float:
    now = now or datetime.now()
    run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if run <= now:
        run += timedelta(days=1)
    return (run - now).total_seconds()


async def run_forever() -> None:
    hour = get_settings().daily_job_hour
    while True:
        wait = seconds_until(hour)
        log.info("Daily job scheduled in %.0f minutes", wait / 60)
        await asyncio.sleep(wait)
        try:
            await asyncio.to_thread(daily.run_all)
        except Exception:
            log.exception("Daily job crashed")


def start() -> asyncio.Task | None:
    if not get_settings().scheduler_enabled:
        return None
    return asyncio.create_task(run_forever())
