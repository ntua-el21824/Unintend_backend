import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..deps import get_db, get_current_user
from ..models import (
    UserRole,
    InternshipPost,
    StudentPostInteraction,
    Decision,
    Application,
    ApplicationStatus,
    CompanyProfile,
    StudentProfilePost,
    CompanyStudentPostInteraction,
    StudentProfile,
    User,
)
from ..schemas import PostResponse, StudentProfilePostResponse
from ..url_utils import to_public_url
from ..departments import normalize_department

router = APIRouter(prefix="/feed", tags=["feed"])

logger = logging.getLogger(__name__)


@router.get("/student", response_model=list[PostResponse])
def student_feed(
    request: Request,
    department: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students have this feed")

    # Hide a post only if the student PASSed it, OR the company has responded to the Application
    # (ACCEPTED/DECLINED). Otherwise keep it visible after LIKE until the other side reacts.
    resolved_app_post_ids = (
        db.query(Application.post_id)
        .filter(Application.student_user_id == current.id)
        .filter(Application.status != ApplicationStatus.PENDING)
        .subquery()
    )

    interactions = (
        db.query(StudentPostInteraction.post_id)
        .join(InternshipPost, InternshipPost.id == StudentPostInteraction.post_id)
        .filter(StudentPostInteraction.student_user_id == current.id)
        .filter(
            (StudentPostInteraction.decision == Decision.PASS)
            | (InternshipPost.id.in_(resolved_app_post_ids))
        )
        .subquery()
    )

    department_filter = normalize_department(department)
    logger.info(
        "/feed/student department=%r normalized=%r",
        department,
        department_filter,
    )

    posts_query = (
        db.query(InternshipPost)
        .filter(InternshipPost.is_active == True)
        .filter(~InternshipPost.id.in_(interactions))
    )

    if department_filter:
        posts_query = posts_query.filter(
            func.trim(func.lower(InternshipPost.department)) == department_filter.lower()
        )

    posts = (
        posts_query
        .order_by(InternshipPost.created_at.desc())
        .limit(50)
        .all()
    )

    out = []
    for p in posts:
        company_name = None
        cp = db.query(CompanyProfile).filter(CompanyProfile.user_id == p.company_user_id).first()
        if cp and cp.company_name:
            company_name = cp.company_name

        company_user: User | None = db.query(User).filter(User.id == p.company_user_id).first()
        company_profile_image_url = company_user.profile_image_url if company_user else None

        # Check if post is saved by current student
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


@router.get("/company", response_model=list[StudentProfilePostResponse])
def company_feed(
    request: Request,
    department: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Feed εταιρίας: επιστρέφει StudentProfilePost (κάρτες φοιτητών σαν posts).
    Εξαιρεί όσα η εταιρία έχει ήδη κάνει LIKE/PASS (decision != NONE).
    """
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies have this feed")

    # For companies:
    # - LIKE/PASS are stored on CompanyStudentPostInteraction.
    # - PASS should hide only until the student updates their profile (StudentProfilePost.updated_at).
    #   After profile changes, the card should re-appear so the company can re-evaluate.
    student_decisions = (
        db.query(StudentPostInteraction.student_user_id, StudentPostInteraction.post_id, StudentPostInteraction.decision)
        .filter(StudentPostInteraction.decision != Decision.NONE)
        .subquery()
    )

    decided = (
        db.query(CompanyStudentPostInteraction.student_post_id)
        .filter(CompanyStudentPostInteraction.company_user_id == current.id)
        .filter(
            # PASS hides only if it's "current" relative to the latest profile update.
            (
                (CompanyStudentPostInteraction.decision == Decision.PASS)
                & (
                    CompanyStudentPostInteraction.student_post_id.in_(
                        db.query(StudentProfilePost.id)
                        .filter(
                            func.coalesce(StudentProfilePost.updated_at, StudentProfilePost.created_at)
                            <= CompanyStudentPostInteraction.decided_at
                        )
                    )
                )
            )
            |
            # For any non-PASS decisions (i.e. LIKE), keep the previous behavior: hide only once the student has also decided.
            (
                (CompanyStudentPostInteraction.decision != Decision.NONE)
                & (CompanyStudentPostInteraction.decision != Decision.PASS)
                & (
                    CompanyStudentPostInteraction.student_post_id.in_(
                        db.query(StudentProfilePost.id)
                        .join(student_decisions, student_decisions.c.student_user_id == StudentProfilePost.student_user_id)
                    )
                )
            )
        )
        .subquery()
    )

    department_filter = normalize_department(department)
    logger.info(
        "/feed/company department=%r normalized=%r",
        department,
        department_filter,
    )

    posts_query = (
        db.query(StudentProfilePost)
        .filter(StudentProfilePost.is_active == True)
        .filter(~StudentProfilePost.id.in_(decided))
    )

    if department_filter:
        posts_query = posts_query.join(
            StudentProfile,
            StudentProfile.user_id == StudentProfilePost.student_user_id,
        ).filter(func.trim(func.lower(StudentProfile.department)) == department_filter.lower())

    posts = (
        posts_query
        .order_by(StudentProfilePost.created_at.desc())
        .limit(50)
        .all()
    )

    out = []
    for p in posts:
        student_user: User | None = db.query(User).filter(User.id == p.student_user_id).first()
        sp: StudentProfile | None = db.query(StudentProfile).filter(StudentProfile.user_id == p.student_user_id).first()

        out.append(StudentProfilePostResponse(
            id=p.id,
            studentUserId=p.student_user_id,
            studentUsername=student_user.username if student_user else None,
            studentName=student_user.name if student_user else None,
            studentSurname=student_user.surname if student_user else None,
            studentProfileImageUrl=to_public_url(student_user.profile_image_url if student_user else None, request),
            university=sp.university if sp else None,
            department=sp.department if sp else None,
            title=p.title,
            description=p.description,
            location=p.location,
            imageUrl=to_public_url(p.image_url, request),
            createdAt=p.created_at,
        ))

    return out
