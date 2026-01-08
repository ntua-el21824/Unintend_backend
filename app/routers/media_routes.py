from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
    User,
    UserRole,
    InternshipPost,
    StudentExperiencePost,
    StudentProfilePost,
)
from ..url_utils import to_public_url

router = APIRouter(prefix="/media", tags=["media"])


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _uploads_root() -> Path:
    # workspace-root/uploads
    return (Path(__file__).resolve().parents[2] / "uploads")


def _save_upload(*, upload: UploadFile, subdir: str) -> str:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    original_name = upload.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use jpg, png, or webp")

    root = _uploads_root()
    target_dir = root / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid4().hex}{ext}"
    target_path = target_dir / file_name

    # Stream to disk
    with target_path.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # URL path served by FastAPI StaticFiles mount
    return f"/uploads/{subdir}/{file_name}"


@router.post("/me/profile-image")
def upload_my_profile_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    url = _save_upload(upload=file, subdir="profiles")
    current.profile_image_url = url
    db.commit()
    return {"profileImageUrl": to_public_url(url, request)}


@router.post("/internship-posts/{post_id}/image")
def upload_internship_post_image(
    post_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can upload images for internship posts")

    post = db.get(InternshipPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.company_user_id != current.id:
        raise HTTPException(status_code=403, detail="Not your post")

    url = _save_upload(upload=file, subdir="internship-posts")
    post.image_url = url
    db.commit()
    return {"imageUrl": to_public_url(url, request)}


@router.post("/student-profile-posts/{student_post_id}/image")
def upload_student_profile_post_image(
    student_post_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can upload images for their profile post")

    post = db.get(StudentProfilePost, student_post_id)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="Student post not found")
    if post.student_user_id != current.id:
        raise HTTPException(status_code=403, detail="Not your post")

    url = _save_upload(upload=file, subdir="student-profile-posts")
    post.image_url = url
    db.commit()
    return {"imageUrl": to_public_url(url, request)}


@router.post("/profile-posts/{post_id}/image")
def upload_student_experience_post_image(
    post_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can upload images for profile posts")

    post = db.get(StudentExperiencePost, post_id)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.student_user_id != current.id:
        raise HTTPException(status_code=403, detail="Not your post")

    url = _save_upload(upload=file, subdir="profile-posts")
    post.image_url = url
    db.commit()
    return {"imageUrl": to_public_url(url, request)}
