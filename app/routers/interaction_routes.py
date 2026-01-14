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
    ConversationParticipant,
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


def create_application_and_conversation_if_needed(
    db: Session,
    student_id: int,
    post: InternshipPost,
    *,
    initial_status: ApplicationStatus = ApplicationStatus.PENDING,
) -> Application:
    app = (
        db.query(Application)
        .filter(Application.post_id == post.id, Application.student_user_id == student_id)
        .first()
    )
    if app:
        return app

    if initial_status == ApplicationStatus.PENDING:
        system_text = PENDING_TEXT
    elif initial_status == ApplicationStatus.ACCEPTED:
        system_text = ACCEPTED_TEXT
    else:
        system_text = DECLINED_TEXT

    app = Application(
        post_id=post.id,
        student_user_id=student_id,
        company_user_id=post.company_user_id,
        status=initial_status,
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
        text=system_text,
    )
    db.add(msg)
    db.flush()

    # Initialize read state for both participants to the initial system message.
    db.add(ConversationParticipant(
        conversation_id=conv.id,
        user_id=student_id,
        last_read_message_id=msg.id,
        updated_at=datetime.utcnow(),
    ))
    db.add(ConversationParticipant(
        conversation_id=conv.id,
        user_id=post.company_user_id,
        last_read_message_id=msg.id,
        updated_at=datetime.utcnow(),
    ))
    db.flush()
    return app


def _company_has_passed_student(db: Session, *, company_user_id: int, student_user_id: int) -> bool:
    spost = (
        db.query(StudentProfilePost)
        .filter(StudentProfilePost.student_user_id == student_user_id)
        .first()
    )
    if not spost:
        return False
    return (
        db.query(CompanyStudentPostInteraction)
        .filter(
            CompanyStudentPostInteraction.company_user_id == company_user_id,
            CompanyStudentPostInteraction.student_post_id == spost.id,
            CompanyStudentPostInteraction.decision == Decision.PASS,
        )
        .first()
        is not None
    )


def _latest_company_post_student_passed(
    db: Session, *, company_user_id: int, student_user_id: int
) -> InternshipPost | None:
    """Returns the most recent InternshipPost (of this company) that the student has PASSed."""
    row = (
        db.query(StudentPostInteraction)
        .join(InternshipPost, InternshipPost.id == StudentPostInteraction.post_id)
        .filter(StudentPostInteraction.student_user_id == student_user_id)
        .filter(StudentPostInteraction.decision == Decision.PASS)
        .filter(InternshipPost.company_user_id == company_user_id)
        .order_by(StudentPostInteraction.decided_at.desc().nullslast(), StudentPostInteraction.id.desc())
        .first()
    )
    if not row:
        return None
    return db.get(InternshipPost, row.post_id)


def _update_pending_application_status_for_company_student_if_any(
    db: Session,
    *,
    company_user_id: int,
    student_user_id: int,
    decision: Decision,
) -> None:
    """
    If there is a pending Application between company and student (created when the student liked a post),
    update it to ACCEPTED/DECLINED based on the company's LIKE/PASS and append a system message.

    Note: If there is no Application yet (company acted first), we do nothing.
    """
    if decision not in (Decision.LIKE, Decision.PASS):
        return

    app = (
        db.query(Application)
        .filter(
            Application.company_user_id == company_user_id,
            Application.student_user_id == student_user_id,
            Application.status == ApplicationStatus.PENDING,
        )
        .order_by(Application.updated_at.desc())
        .first()
    )
    if not app:
        # If student PASSed first (on one of the company's posts) and company is now reacting,
        # create a declined conversation so both sides get the "not a match" system message.
        passed_post = _latest_company_post_student_passed(
            db, company_user_id=company_user_id, student_user_id=student_user_id
        )
        if passed_post:
            create_application_and_conversation_if_needed(
                db,
                student_user_id,
                passed_post,
                initial_status=ApplicationStatus.DECLINED,
            )
        return

    new_status = ApplicationStatus.ACCEPTED if decision == Decision.LIKE else ApplicationStatus.DECLINED
    if app.status == new_status:
        return

    app.status = new_status
    app.updated_at = datetime.utcnow()

    conv = db.query(Conversation).filter(Conversation.application_id == app.id).first()
    if not conv:
        # Defensive: the app should always have a conversation if it was created via LIKE.
        return

    system_text = ACCEPTED_TEXT if new_status == ApplicationStatus.ACCEPTED else DECLINED_TEXT
    db.add(
        Message(
            conversation_id=conv.id,
            type=MessageType.SYSTEM,
            sender_user_id=None,
            text=system_text,
        )
    )


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

    # If the company already PASSed this student (from company feed), then regardless of
    # whether the student presses LIKE or PASS now, this should result in a "not a match" chat.
    if _company_has_passed_student(db, company_user_id=post.company_user_id, student_user_id=current.id):
        create_application_and_conversation_if_needed(
            db,
            current.id,
            post,
            initial_status=ApplicationStatus.DECLINED,
        )
    elif row.decision == Decision.LIKE:
        # Άμεσο "Ready to connect?" όταν ο φοιτητής κάνει LIKE
        create_application_and_conversation_if_needed(db, current.id, post, initial_status=ApplicationStatus.ACCEPTED)

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

    # Sync company decision to any pending Application (student liked one of this company's posts).
    _update_pending_application_status_for_company_student_if_any(
        db,
        company_user_id=current.id,
        student_user_id=spost.student_user_id,
        decision=row.decision,
    )

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

    _update_pending_application_status_for_company_student_if_any(
        db,
        company_user_id=current.id,
        student_user_id=spost.student_user_id,
        decision=row.decision,
    )

    db.commit()
    return {"ok": True}
