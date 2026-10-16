"""Open a buyer-vendor conversation for an application."""

import logging

from msflib.conversation.contracts.participants import Participant
from msflib.conversation.contracts.scope import ConversationScope
from msflib.conversation.models import ConversationCreate
from msflib.conversation.models.enums import ConversationKind, MemberKind, MemberRole
from msflib.conversation.services.channels import ChannelService
from msflib.conversation.services.membership import MembershipService
from msflib.tenancy.resolver import resolve_default_tenant_id
from sqlmodel import Session

from app.core.config import settings
from app.models import Account

logger = logging.getLogger(__name__)


def open_application_channel(
    session: Session,
    *,
    application_id: int,
    tender_title: str,
    buyer: Account,
    vendor: Account,
) -> str | None:
    tenant_id = resolve_default_tenant_id(
        session,
        settings=settings.scope("TENANCY"),
        create_if_missing=False,
    )
    if tenant_id is None:
        logger.warning("Skipped application channel because the default tenant is missing.")
        return None

    workspace_id = buyer.current_workspace_id or vendor.current_workspace_id
    scope = ConversationScope(tenant_id=int(tenant_id), workspace_id=workspace_id)
    owner = Participant(kind=MemberKind.user, id=str(buyer.id), tenant_id=int(tenant_id))
    conversation, membership = ChannelService().create_channel(
        session,
        scope=scope,
        data=ConversationCreate(
            kind=ConversationKind.channel,
            name=f"Application {application_id}",
            slug=f"application-{application_id}",
            topic=tender_title,
            purpose="Buyer and vendor discussion for this application.",
        ),
        created_by=owner,
    )
    MembershipService().invite(
        session,
        conversation=conversation,
        inviter_membership=membership,
        invitee=Participant(kind=MemberKind.user, id=str(vendor.id), tenant_id=int(tenant_id)),
        role=MemberRole.member,
    )
    return conversation.public_id
