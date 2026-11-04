"""reminders.sync {document_id} and the periodic reminders.scan (sent from 07:00 local time)."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from docuhive import jobs, reminders
from docuhive.ai.settings import get_ai_settings

SEND_FROM_HOUR = 7


@jobs.handler("reminders.sync", queue="ai")
def run_sync(payload: dict, ctx: Any) -> None:
    reminders.sync(payload["document_id"])


@jobs.periodic("reminders.scan", every=timedelta(hours=1), queue="default")
def run_scan(payload: dict, ctx: Any) -> None:
    # ponytail: hourly tick + an hour gate instead of a cron expression; jobs only offer `every`.
    now = datetime.now(ZoneInfo(get_ai_settings().tz))
    if now.hour >= SEND_FROM_HOUR:
        reminders.scan(now.date())
