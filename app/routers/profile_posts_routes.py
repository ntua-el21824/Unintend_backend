from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..models import User, UserRole, StudentExperiencePost
from ..schemas import StudentExperiencePostCreateRequest, StudentExperiencePostResponse
from ..url_utils import to_public_url

router = APIRouter(prefix="/profile-posts", tags=["profile-posts"])


def _ensure_student_role(current: User):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can manage profile posts")


@router.post("", response_model=StudentExperiencePostResponse)
def create_profile_post(
    request: Request,
    req: StudentExperiencePostCreateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _ensure_student_role(current)

    post = StudentExperiencePost(
        student_user_id=current.id,
        title=req.title,
        description=req.description,
        category=req.category,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return StudentExperiencePostResponse(
        id=post.id,
        studentUserId=post.student_user_id,
        title=post.title,
        description=post.description,
        category=post.category,
        imageUrl=to_public_url(post.image_url, request),
        createdAt=post.created_at,
    )


@router.get("/me", response_model=list[StudentExperiencePostResponse])
def list_my_profile_posts(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _ensure_student_role(current)

    posts = (
        db.query(StudentExperiencePost)
        .filter(StudentExperiencePost.student_user_id == current.id)
        .filter(StudentExperiencePost.is_active == True)
        .order_by(StudentExperiencePost.created_at.desc())
        .all()
    )

    return [
        StudentExperiencePostResponse(
            id=p.id,
            studentUserId=p.student_user_id,
            title=p.title,
            description=p.description,
            category=p.category,
            imageUrl=to_public_url(p.image_url, request),
            createdAt=p.created_at,
        )
        for p in posts
    ]


@router.get("/{student_user_id}", response_model=list[StudentExperiencePostResponse])
def list_profile_posts_for_student(
    student_user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Either role can view profile posts; only need auth to know viewer
    posts = (
        db.query(StudentExperiencePost)
        .filter(StudentExperiencePost.student_user_id == student_user_id)
        .filter(StudentExperiencePost.is_active == True)
        .order_by(StudentExperiencePost.created_at.desc())
        .all()
    )

    return [
        StudentExperiencePostResponse(
            id=p.id,
            studentUserId=p.student_user_id,
            title=p.title,
            description=p.description,
            category=p.category,
            imageUrl=to_public_url(p.image_url, request),
            createdAt=p.created_at,
        )
        for p in posts
    ]


@router.delete("/{post_id}", status_code=204)
def delete_profile_post(
    post_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _ensure_student_role(current)

    post = (
        db.query(StudentExperiencePost)
        .filter(StudentExperiencePost.id == post_id)
        .filter(StudentExperiencePost.is_active == True)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Profile post not found")

    if post.student_user_id != current.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    post.is_active = False
    db.add(post)
    db.commit()
    return Response(status_code=204)
