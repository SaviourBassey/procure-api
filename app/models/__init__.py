# Register msflib tables before SQLModel.metadata.create_all runs.
import msflib.notifications.models  # noqa: E402
import msflib.payments.models  # noqa: E402

# AI provider profiles reference tenant. Import it before create_all.
import msflib.tenancy.models.tenant
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