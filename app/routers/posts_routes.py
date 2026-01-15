from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..models import UserRole, InternshipPost, CompanyProfile, User, StudentPostInteraction
from ..schemas import PostCreateRequest, PostResponse
from ..url_utils import to_public_url
from ..departments import CANONICAL_DEPARTMENTS, normalize_department

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostResponse)
def create_post(
    request: Request,
    req: PostCreateRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can create posts")

    department = normalize_department(req.department)
    if department is not None and department not in CANONICAL_DEPARTMENTS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Invalid department",
                "allowed": list(CANONICAL_DEPARTMENTS),
                "received": req.department,
            },
        )

    post = InternshipPost(
        company_user_id=current.id,
        title=req.title,
        description=req.description,
        location=req.location,
        department=department,
        is_active=True,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    company_name = None
    if current.company_profile and current.company_profile.company_name:
        company_name = current.company_profile.company_name

    return PostResponse(
        id=post.id,
        companyUserId=post.company_user_id,
        companyName=company_name,
        companyProfileImageUrl=to_public_url(current.profile_image_url, request),
        title=post.title,
        description=post.description,
        location=post.location,
        department=post.department,
        imageUrl=to_public_url(post.image_url, request),
        saved=False,
        createdAt=post.created_at,
    )


@router.get("/me", response_model=list[PostResponse])
def list_my_company_posts(
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Return all posts created by the current company."""
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can view their posts")

    posts = (
        db.query(InternshipPost)
        .filter(InternshipPost.company_user_id == current.id)
        .filter(InternshipPost.is_active == True)
        .order_by(InternshipPost.created_at.desc())
        .all()
    )

    company_name = None
    if current.company_profile and current.company_profile.company_name:
        company_name = current.company_profile.company_name

    return [
        PostResponse(
            id=p.id,
            companyUserId=p.company_user_id,
            companyName=company_name,
            companyProfileImageUrl=to_public_url(current.profile_image_url, request),
            title=p.title,
            description=p.description,
            location=p.location,
            department=p.department,
            imageUrl=to_public_url(p.image_url, request),
            saved=False,
            createdAt=p.created_at,
        )
        for p in posts
    ]


@router.get("/company/{company_user_id}", response_model=list[PostResponse])
def list_company_posts(
    company_user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Return all active posts for a company (for profile/view screens)."""
    posts = (
        db.query(InternshipPost)
        .filter(InternshipPost.company_user_id == company_user_id)
        .filter(InternshipPost.is_active == True)
        .order_by(InternshipPost.created_at.desc())
        .all()
    )

    company_name = None
    cp = db.query(CompanyProfile).filter(CompanyProfile.user_id == company_user_id).first()
    if cp and cp.company_name:
        company_name = cp.company_name

    cu: User | None = db.query(User).filter(User.id == company_user_id).first()
    company_profile_image_url = cu.profile_image_url if cu else None

    out = []
    for p in posts:
        # Check if current user is student and has saved this post
        is_saved = False
        if current.role == UserRole.STUDENT:
            interaction = db.query(StudentPostInteraction).filter(
                StudentPostInteraction.student_user_id == current.id,
                StudentPostInteraction.post_id == p.id
            ).first()
            is_saved = interaction.saved if interaction else False

        out.append(PostResponse(
            id=p.id,
            companyUserId=p.company_user_id,
            companyName=company_name,
            companyProfileImageUrl=to_public_url(company_profile_image_url, request),
            title=p.title,
            description=p.description,
            location=p.location,
            department=p.department,
            imageUrl=to_public_url(p.image_url, request),
            saved=is_saved,
            createdAt=p.created_at,
        ))
    return out


@router.delete("/{post_id}", status_code=204)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can delete posts")

    post = db.get(InternshipPost, post_id)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.company_user_id != current.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Soft-delete to avoid FK issues with interactions/applications
    post.is_active = False
    db.commit()
    return Response(status_code=204)
