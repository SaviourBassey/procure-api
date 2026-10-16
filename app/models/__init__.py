# Register msflib tables before SQLModel.metadata.create_all runs.
import msflib.ai_core.models  # noqa: E402
import msflib.conversation.models  # noqa: E402
import msflib.documents.models  # noqa: E402
import msflib.drivelink.models  # noqa: E402
import msflib.ingestion.models  # noqa: E402
import msflib.knowledge.integrations.models  # noqa: E402
import msflib.knowledge.models  # noqa: E402
import msflib.notifications.models  # noqa: E402
import msflib.payments.models  # noqa: E402
import msflib.tenancy.models.tenant  # noqa: E402
import msflib.workspace_config.models  # noqa: E402
import msflib.workspace_notifications.models  # noqa: E402
import msflib.workspaces.models.user  # noqa: E402
import msflib.workspaces.models.workspace  # noqa: E402
from msflib.account.models.account import Account, Profile

from app.models.analysis import ApplicationAnalysis
from app.models.application import (
    ApplicationDocument,
    ApplicationItemQuote,
    ApplicationRequirementResponse,
    TenderApplication,
)
from app.models.commerce import (
    ProcurementOrder,
    Wallet,
    WalletEntry,
    Withdrawal,
)
from app.models.onboarding import (
    BuyerOnboarding,
    VendorCategory,
    VendorDocument,
    VendorGalleryItem,
    VendorOnboarding,
)
from app.models.tender import (
    Tender,
    TenderItem,
    TenderProductRequirement,
    TenderRequiredDocument,
)

__all__ = [
    "Account",
    "ApplicationAnalysis",
    "ApplicationDocument",
    "ApplicationItemQuote",
    "ApplicationRequirementResponse",
    "BuyerOnboarding",
    "ProcurementOrder",
    "Profile",
    "Tender",
    "TenderApplication",
    "TenderItem",
    "TenderProductRequirement",
    "TenderRequiredDocument",
    "VendorCategory",
    "VendorDocument",
    "VendorGalleryItem",
    "VendorOnboarding",
    "Wallet",
    "WalletEntry",
    "Withdrawal",
]