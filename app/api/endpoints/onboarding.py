
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlmodel import Session, select

from app.db.session import get_session
from app.dependencies import auth_deps
from app.models import (
    Account,
    BuyerOnboarding,
    VendorOnboarding,
    VendorCategory,
    VendorDocument,
    VendorGalleryItem,
)
from app.services.cloudinary_storage import upload_file

from pydantic import BaseModel, Field


class BuyerOnboardingRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=300)


onboarding_router = APIRouter()


DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def get_account_type(account: Account) -> str | None:
    data = getattr(account, "data", None) or {}

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    if isinstance(data, dict):
        value = data.get("account_type")
        return str(value).lower() if value else None

    return None


def require_account_type(account: Account, expected: str) -> None:
    if get_account_type(account) != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This endpoint is only available to {expected} accounts.",
        )


@onboarding_router.post(
    "/buyer",
    status_code=status.HTTP_201_CREATED,
    tags=["Onboarding"],
)
def onboard_buyer(
    payload: BuyerOnboardingRequest,
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    require_account_type(current_account, "buyer")

    existing = session.exec(
        select(BuyerOnboarding).where(
            BuyerOnboarding.account_id == str(current_account.id)
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Buyer onboarding has already been completed.",
        )

    # An account must not have both buyer and vendor profiles.
    vendor_profile = session.exec(
        select(VendorOnboarding).where(
            VendorOnboarding.account_id == str(current_account.id)
        )
    ).first()

    if vendor_profile:
        raise HTTPException(
            status_code=409,
            detail="This account already has a vendor profile.",
        )

    buyer = BuyerOnboarding(
        account_id=str(current_account.id),
        organization_name=payload.organization_name.strip(),
        location=payload.location.strip(),
    )

    session.add(buyer)
    session.commit()
    session.refresh(buyer)

    return {
        "message": "Buyer onboarding completed successfully.",
        "onboarding_completed": True,
        "account_type": "buyer",
        "profile": {
            "id": buyer.id,
            "organization_name": buyer.organization_name,
            "location": buyer.location,
            "completed_at": buyer.completed_at,
        },
    }


@onboarding_router.post(
    "/vendor",
    status_code=status.HTTP_201_CREATED,
    tags=["Onboarding"],
)
async def onboard_vendor(
    business_name: str = Form(..., min_length=2, max_length=200),
    location: str = Form(..., min_length=2, max_length=300),
    categories: list[str] = Form(...),
    document_names: list[str] = Form(default=[]),
    documents: list[UploadFile] | None = File(default=None),
    gallery: list[UploadFile] | None = File(default=None),
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    require_account_type(current_account, "vendor")

    account_id = str(current_account.id)

    existing = session.exec(
        select(VendorOnboarding).where(
            VendorOnboarding.account_id == account_id
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Vendor onboarding has already been completed.",
        )

    buyer_profile = session.exec(
        select(BuyerOnboarding).where(
            BuyerOnboarding.account_id == account_id
        )
    ).first()

    if buyer_profile:
        raise HTTPException(
            status_code=409,
            detail="This account already has a buyer profile.",
        )

    clean_categories = list(
        dict.fromkeys(
            category.strip()
            for category in categories
            if category.strip()
        )
    )

    if not clean_categories:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one business category.",
        )

    documents = documents or []
    gallery = gallery or []
    document_names = document_names or []

    if len(documents) != len(document_names):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one name for each document.",
        )

    if any(not name.strip() for name in document_names):
        raise HTTPException(
            status_code=422,
            detail="Document names cannot be empty.",
        )

    # Upload files before saving their metadata.
    uploaded_documents = []
    uploaded_gallery = []

    for file, name in zip(documents, document_names):
        uploaded = await upload_file(
            file,
            folder=f"procure/vendors/{account_id}/documents",
            allowed_types=DOCUMENT_TYPES,
        )
        uploaded_documents.append((name.strip(), uploaded))

    for file in gallery:
        uploaded = await upload_file(
            file,
            folder=f"procure/vendors/{account_id}/gallery",
            allowed_types=IMAGE_TYPES,
        )
        uploaded_gallery.append(uploaded)

    vendor = VendorOnboarding(
        account_id=account_id,
        business_name=business_name.strip(),
        location=location.strip(),
    )

    try:
        session.add(vendor)
        session.flush()

        for category_name in clean_categories:
            session.add(
                VendorCategory(
                    vendor_id=vendor.id,
                    name=category_name,
                )
            )

        for name, uploaded in uploaded_documents:
            session.add(
                VendorDocument(
                    vendor_id=vendor.id,
                    name=name,
                    url=uploaded["url"],
                    public_id=uploaded["public_id"],
                    file_format=uploaded["format"],
                    size_bytes=uploaded["size"],
                )
            )

        for uploaded in uploaded_gallery:
            session.add(
                VendorGalleryItem(
                    vendor_id=vendor.id,
                    url=uploaded["url"],
                    public_id=uploaded["public_id"],
                    file_format=uploaded["format"],
                )
            )

        session.commit()
        session.refresh(vendor)

    except Exception:
        session.rollback()
        raise

    return {
        "message": "Vendor onboarding completed successfully.",
        "onboarding_completed": True,
        "account_type": "vendor",
        "profile": {
            "id": vendor.id,
            "business_name": vendor.business_name,
            "location": vendor.location,
            "categories": clean_categories,
            "documents": [
                {
                    "name": name,
                    "url": uploaded["url"],
                }
                for name, uploaded in uploaded_documents
            ],
            "gallery": [
                {"url": uploaded["url"]}
                for uploaded in uploaded_gallery
            ],
            "completed_at": vendor.completed_at,
        },
    }


@onboarding_router.get("/me", tags=["Onboarding"])
def get_my_onboarding(
    current_account: Account = Depends(auth_deps.get_current_account),
    session: Session = Depends(get_session),
):
    account_id = str(current_account.id)
    account_type = get_account_type(current_account)

    if account_type == "buyer":
        buyer = session.exec(
            select(BuyerOnboarding).where(
                BuyerOnboarding.account_id == account_id
            )
        ).first()

        if not buyer:
            return {
                "account_type": "buyer",
                "onboarding_completed": False,
                "profile": None,
            }

        return {
            "account_type": "buyer",
            "onboarding_completed": True,
            "profile": {
                "id": buyer.id,
                "organization_name": buyer.organization_name,
                "location": buyer.location,
                "completed_at": buyer.completed_at,
            },
        }

    if account_type == "vendor":
        vendor = session.exec(
            select(VendorOnboarding).where(
                VendorOnboarding.account_id == account_id
            )
        ).first()

        if not vendor:
            return {
                "account_type": "vendor",
                "onboarding_completed": False,
                "profile": None,
            }

        categories = session.exec(
            select(VendorCategory).where(
                VendorCategory.vendor_id == vendor.id
            )
        ).all()

        documents = session.exec(
            select(VendorDocument).where(
                VendorDocument.vendor_id == vendor.id
            )
        ).all()

        gallery = session.exec(
            select(VendorGalleryItem).where(
                VendorGalleryItem.vendor_id == vendor.id
            )
        ).all()

        return {
            "account_type": "vendor",
            "onboarding_completed": True,
            "profile": {
                "id": vendor.id,
                "business_name": vendor.business_name,
                "location": vendor.location,
                "categories": [
                    category.name for category in categories
                ],
                "documents": [
                    {"id": doc.id, "name": doc.name, "url": doc.url}
                    for doc in documents
                ],
                "gallery": [
                    {"id": item.id, "url": item.url}
                    for item in gallery
                ],
                "completed_at": vendor.completed_at,
            },
        }

    raise HTTPException(
        status_code=403,
        detail="Unsupported account type for onboarding.",
    )
