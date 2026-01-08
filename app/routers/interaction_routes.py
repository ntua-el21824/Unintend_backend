from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..models import (
    UserRole, Decision,
    StudentPostInteraction,
    InternshipPost, Application, ApplicationStatus,
    Conversation, Message, MessageType,
    StudentProfilePost,
    CompanyStudentPostInteraction,
)
from ..schemas import StudentDecisionRequest, CompanyDecisionStudentPostRequest, CompanyDecisionStudentRequest

router = APIRouter(prefix="", tags=["interactions"])


PENDING_TEXT = "Message still pending"
ACCEPTED_TEXT = "Ready to connect?"
DECLINED_TEXT = "Unfortunately this was not a match, keep searching!"


def ensure_student_interaction_row(db: Session, student_user_id: int, post_id: int) -> StudentPostInteraction:
    row = (
        db.query(StudentPostInteraction)
        .filter(StudentPostInteraction.student_user_id == student_user_id, StudentPostInteraction.post_id == post_id)
        .first()
    )
    if not row:
        row = StudentPostInteraction(student_user_id=student_user_id, post_id=post_id)
        db.add(row)
        db.flush()
    return row


def ensure_company_studentpost_interaction(db: Session, company_user_id: int, student_post_id: int) -> CompanyStudentPostInteraction:
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


def create_application_and_conversation_if_needed(db: Session, student_id: int, post: InternshipPost) -> Application:
    app = (
        db.query(Application)
        .filter(Application.post_id == post.id, Application.student_user_id == student_id)
        .first()
    )
    if app:
        return app

    app = Application(
        post_id=post.id,
        student_user_id=student_id,
        company_user_id=post.company_user_id,
        status=ApplicationStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(app)
    db.flush()

    conv = Conversation(application_id=app.id)
    db.add(conv)
    db.flush()

    msg = Message(
        conversation_id=conv.id,
        type=MessageType.SYSTEM,
        sender_user_id=None,
        text=PENDING_TEXT,
    )
    db.add(msg)
    db.flush()
    return app


@router.post("/decisions/student/post")
def student_decision_post(
    req: StudentDecisionRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if current.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can decide on posts")

    post = db.get(InternshipPost, req.postId)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="Post not found")

    row = ensure_student_interaction_row(db, current.id, post.id)
    row.decision = Decision(req.decision)
    row.decided_at = datetime.utcnow()

    if row.decision == Decision.LIKE:
        create_application_and_conversation_if_needed(db, current.id, post)

    db.commit()
    return {"ok": True}


@router.post("/decisions/company/student-post")
def company_decision_student_post(
    req: CompanyDecisionStudentPostRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Company κάνει LIKE/PASS σε StudentProfilePost.
    (Σημ.: Το matching/chat με application το κρατάμε ξεχωριστό βήμα.)
    """
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can decide on student posts")

    spost = db.get(StudentProfilePost, req.studentPostId)
    if not spost or not spost.is_active:
        raise HTTPException(status_code=404, detail="Student post not found")

    row = ensure_company_studentpost_interaction(db, current.id, spost.id)
    row.decision = Decision(req.decision)
    row.decided_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


@router.post("/decisions/company/student")
def company_decision_student(
    req: CompanyDecisionStudentRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """
    Company decides LIKE/PASS given a studentUserId; resolves the student's profile post.
    """
    if current.role != UserRole.COMPANY:
        raise HTTPException(status_code=403, detail="Only companies can decide on students")

    spost = (
        db.query(StudentProfilePost)
        .filter(StudentProfilePost.student_user_id == req.studentUserId)
        .first()
    )
    if not spost or not spost.is_active:
        raise HTTPException(status_code=404, detail="Student post not found")

    row = ensure_company_studentpost_interaction(db, current.id, spost.id)
    row.decision = Decision(req.decision)
    row.decided_at = datetime.utcnow()

    db.commit()
    return {"ok": True}
