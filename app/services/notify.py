import logging

from sqlmodel import Session

from app.core.config import settings
from app.models import Account

logger = logging.getLogger(__name__)


def notify_accounts(
    session: Session,
    *,
    recipients: list[Account],
    title: str,
    message: str,
    sender: Account | None = None,
) -> bool:
    """Persist an in-app notification through msflib-notifications.

    Returns False when delivery fails. Callers that already committed a
    business change should keep that change and surface the failure separately.
    """
    if not recipients:
        return False

    from msflib.notifications.models import (
        NotificationChannel,
        NotificationCreate,
        NotificationType,
    )
    from msflib.notifications.service.notification import (
        dispatch_account_notifications,
    )

    try:
        dispatch_account_notifications(
            session=session,
            settings=settings,
            data=NotificationCreate(
                title=title,
                message=message,
                channels=[NotificationChannel.inapp],
            ),
            n_type=NotificationType.system,
            sender=sender,
            receivers=recipients,
        )
    except Exception:
        logger.exception("Failed to send notification: %s", title)
        return False

    return True
