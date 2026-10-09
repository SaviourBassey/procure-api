
import os

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file


def configure_cloudinary() -> None:
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        raise HTTPException(
            status_code=500,
            detail="File storage is not configured.",
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


async def upload_file(
    file: UploadFile,
    *,
    folder: str,
    allowed_types: set[str],
) -> dict:
    content_type = (file.content_type or "").lower()

    if content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.filename}",
        )

    content = await file.read(MAX_FILE_SIZE + 1)

    if not content:
        raise HTTPException(
            status_code=400,
            detail=f"{file.filename} is empty.",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"{file.filename} exceeds the 10 MB limit.",
        )

    configure_cloudinary()

    try:
        result = cloudinary.uploader.upload(
            content,
            folder=folder,
            resource_type="image" if content_type.startswith("image/") else "raw",
            use_filename=False,
            unique_filename=True,
        )
    except Exception as exc:
        # Avoid returning provider credentials or internal errors.
        raise HTTPException(
            status_code=502,
            detail="Unable to upload file. Please try again.",
        ) from exc
    finally:
        await file.close()

    return {
        "url": result["secure_url"],
        "public_id": result["public_id"],
        "format": result.get("format"),
        "size": result.get("bytes"),
    }
