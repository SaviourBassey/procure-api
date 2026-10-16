"""Host-app listeners for msflib account events and procurement events."""

import logging

from msflib.account.eventbus import EventName
from msflib.eventbus import emitter

from app.services.notify import notify_accounts
from app.services.organization import ensure_membership

logger = logging.getLogger(__name__)


def register_platform_listeners(app_emitter) -> None:
    @emitter.on(EventName.ACCOUNT_CREATED_PRE_EMAIL)
    def join_default_workspace(account, options):
        session = options.get("session")
        if session is None:
            return
        ensure_membership(session, account)

    @app_emitter.on("tender-published")
    def record_tender_published(tender_id: int) -> None:
        logger.info("Tender %s published", tender_id)


def publish_tender(app, session, tender_id: int, buyer) -> None:
    from msflib.eventbus import get_app_emitter

    get_app_emitter(app).emit_optional("tender-published", tender_id)
    notify_accounts(
        session,
        recipients=[buyer],
        title="Tender published",
        message=f"Tender {tender_id} is open for vendor applications.",
        sender=buyer,
    )
