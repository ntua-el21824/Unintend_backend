# app/routers/saves_routes.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..models import (
    User,
    UserRole,
    InternshipPost,
    CompanyProfile,
    StudentProfile,
    StudentPostInteraction,
    StudentProfilePost,
    CompanyStudentPostInteraction,
)
from ..schemas import StudentSaveRequest  # postId + saved

from typing import Optional
from pydantic import BaseModel


class CompanySaveStudentRequest(BaseModel):
    studentUserId: Optional[int] = None
    studentPostId: Optional[int] = None
    saved: bool


router = APIRouter(prefix="/saves", tags=["saves"])


def ensure_student_post_interaction_row(db: Session, student_user_id: int, post_id: int) -> StudentPostInteraction:
    row = (
        db.query(StudentPostInteraction)
        .filter(
            StudentPostInteraction.student_user_id == student_user_id,
            StudentPostInteraction.post_id == post_id,
        )
        .first()
    )
    if not row:
        row = StudentPostInteraction(student_user_id=student_user_id, post_id=post_id)
        db.add(row)
        db.flush()
    return row


def ensure_company_studentpost_interaction_row(db: Session, company_user_id: int, student_post_id: int) -> CompanyStudentPostInteraction:
    row = (
        db.query(CompanyStudentPostInteraction)
        .filter(
            CompanyStudentPostInteraction.company_user_id == company_user_id,
            CompanyStudentPostInteraction.student_post_id == student_post_id,
        )
        .first()
    )
    if not row:
        row = CompanyStudentPostInteraction(company_user_id=company_user_id, student_post_id=student_post_id)
        db.add(row)
        db.flush()
    return row


def ensure_student_profile_post(db: Session, student: User, sp: StudentProfile | None = None) -> StudentProfilePost:
    """Ensure a StudentProfilePost exists for the student; create from profile fields if missing."""
    spost = (
        db.query(StudentProfilePost)
        .filter(StudentProfilePost.student_user_id == student.id)
        .first()
    )
    if spost:
        return spost

    if sp is None:
        sp = db.query(StudentProfile).filter(StudentProfile.user_id == student.id).first()

    title = "Student Profile"
    if sp and sp.studies:
        title = sp.studies
    elif student.name:
        title = f"{student.name} {student.surname or ''}".strip()

    desc_parts = []
    if sp and sp.bio:
        desc_parts.append(sp.bio)
    if sp and sp.skills:
        desc_parts.append(f"Skills: {sp.skills}")
    if sp and sp.studies:
        desc_parts.append(f"Studies: {sp.studies}")
    if sp and sp.experience:
        desc_parts.append(f"Experience: {sp.experience}")
    if sp and (sp.university or sp.department):
        desc_parts.append(f"University: {sp.university or ''} ({sp.department or ''})".strip())

    description = "\n".join([p for p in desc_parts if p]) or "Student profile"

    spost = StudentProfilePost(
        student_user_id=student.id,
        title=title,
        description=description,
        location=None,
        is_active=True,
    )
    db.add(spost)
    db.flush()
    return spost


# -----------------------------
# STUDENT: GET saved internship posts
# -----------------------------
@router.get("/student/posts")
def list_saved_posts_for_student(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can view saved posts")

    rows = (
        db.query(StudentPostInteraction, InternshipPost)
        .join(InternshipPost, InternshipPost.id == StudentPostInteraction.post_id)
        .filter(StudentPostInteraction.student_user_id == current.id)
        .filter(StudentPostInteraction.saved == True)
        .order_by(StudentPostInteraction.saved_at.desc().nullslast())
        .all()
    )

    out = []
    for (spi, post) in rows:
        cp = (
            db.query(CompanyProfile)
            .filter(CompanyProfile.user_id == post.company_user_id)
            .first()
        )
        out.append(
            {
                "postId": post.id,
                "companyUserId": post.company_user_id,
                "companyName": (cp.company_name if cp else None),
                "title": post.title,
                "location": post.location,
                "department": getattr(post, "department", None),
                "description": post.description,
                "savedAt": spi.saved_at.isoformat() if spi.saved_at else None,
            }
        )
    return out


# -----------------------------
# STUDENT: POST save/unsave internship post
# -----------------------------
@router.post("/student/post")
def set_saved_post_for_student(
    req: StudentSaveRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can save posts")

    post = db.get(InternshipPost, req.postId)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    row = ensure_student_post_interaction_row(db, current.id, post.id)
    row.saved = req.saved
    row.saved_at = datetime.utcnow() if req.saved else None

    db.commit()
    return {"ok": True}


# -----------------------------
# COMPANY: GET saved student "posts" (profiles)
# -----------------------------
@router.get("/company/student-posts")
def list_saved_students_for_company(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can view saved students")

    rows = (
        db.query(CompanyStudentPostInteraction, StudentProfilePost, User, StudentProfile)
        .join(StudentProfilePost, StudentProfilePost.id == CompanyStudentPostInteraction.student_post_id)
        .join(User, User.id == StudentProfilePost.student_user_id)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .filter(CompanyStudentPostInteraction.company_user_id == current.id)
        .filter(CompanyStudentPostInteraction.saved == True)
        .order_by(CompanyStudentPostInteraction.saved_at.desc().nullslast())
        .all()
    )

    out = []
    for (csi, spost, student_user, sp) in rows:
        out.append(
            {
                "studentPostId": spost.id,
                "studentUserId": student_user.id,
                "studentUsername": student_user.username,
                "studentName": student_user.name,
                "studentSurname": student_user.surname,
                "university": sp.university if sp else None,
                "department": sp.department if sp else None,
                "description": sp.bio if (sp and sp.bio) else "",
                "skills": sp.skills if sp else None,  # ✅ string όπως θες
                "savedAt": csi.saved_at.isoformat() if csi.saved_at else None,
            }
        )
    return out


# Alias for UI expectations: same payload, different path
@router.get("/company/students")
def list_saved_students_for_company_alias(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return list_saved_students_for_company(db=db, current=current)


# -----------------------------
# COMPANY: POST save/unsave student profile "post"
# -----------------------------
@router.post("/company/student-post")
def set_saved_student_for_company(
    req: CompanySaveStudentRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can save students")

    student = None
    spost = None

    if req.studentPostId is not None:
        spost = db.get(StudentProfilePost, req.studentPostId)
        if not spost:
            raise HTTPException(status_code=404, detail="Student post not found")
        student = db.get(User, spost.student_user_id)
    elif req.studentUserId is not None:
        student = db.get(User, req.studentUserId)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        spost = ensure_student_profile_post(db, student)
    else:
        raise HTTPException(status_code=400, detail="Provide studentUserId or studentPostId")

    if not student or student.role != UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="Student not found")

    row = ensure_company_studentpost_interaction_row(db, current.id, spost.id)
    row.saved = req.saved
    row.saved_at = datetime.utcnow() if req.saved else None

    db.commit()
    return {"ok": True}


# Convenience alias using studentUserId (same body), resolves profile post internally
@router.post("/company/student")
def set_saved_student_for_company_alias(
    req: CompanySaveStudentRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return set_saved_student_for_company(req=req, db=db, current=current)
