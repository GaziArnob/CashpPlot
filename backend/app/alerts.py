"""Owner alerts. Delivery is mocked: each alert is appended to a JSON-lines file and audited.

Plug a real channel in `deliver` (SMS gateway, WhatsApp Business API, email) when one is available.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import audit
from app.models import Business, utcnow

log = logging.getLogger(__name__)


def deliver(business: Business, subject: str, message: str) -> str:
    path = Path(get_settings().alerts_log_path)
    record = {"at": utcnow().isoformat(), "business_id": business.id, "to": business.owner.email,
              "subject": subject, "message": message, "channel": "mock"}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("Alert for business %s: %s", business.id, subject)
    return "mock"


def send(db: Session, business: Business, subject: str, message: str) -> None:
    channel = deliver(business, subject, message)
    audit(db, "alert_sent", "system", business_id=business.id, target=f"{channel}:{subject}")
