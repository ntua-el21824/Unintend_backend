from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func

from ..deps import get_db, get_current_user
from ..models import (
    UserRole, Application, Conversation, Message,
    MessageType, ApplicationStatus, InternshipPost, User,
    ConversationParticipant,
)
from ..schemas import ApplicationListItem, SetApplicationStatusRequest

router = APIRouter(prefix="/applications", tags=["applications"])

PENDING_TEXT = "Message still pending"
ACCEPTED_TEXT = "Ready to connect?"
DECLINED_TEXT = "Unfortunately this was not a match, keep searching!"


def status_to_system_text(status: ApplicationStatus) -> str:
    if status == ApplicationStatus.PENDING:
        return PENDING_TEXT
    if status == ApplicationStatus.ACCEPTED:
        return ACCEPTED_TEXT
    return DECLINED_TEXT


@router.get("", response_model=list[ApplicationListItem])
def list_applications(
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    # Student: applications where student_user_id = current
    # Company: applications where company_user_id = current
    q = db.query(Application)
    if current.role == UserRole.STUDENT:
        q = q.filter(Application.student_user_id == current.id)
    else:
        q = q.filter(Application.company_user_id == current.id)

    apps = q.order_by(Application.updated_at.desc()).limit(50).all()

    out = []
    for a in apps:
        conv = db.query(Conversation).filter(Conversation.application_id == a.id).first()
        if not conv:
            continue

        # Backfill participant state for existing conversations (seeded to last message so users
        # don't suddenly see lots of unread after this feature ships).
        part = (
            db.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.user_id == current.id,
            )
            .first()
        )
        if not part:
            last_msg_id = (
                db.query(func.max(Message.id))
                .filter(Message.conversation_id == conv.id)
                .scalar()
            )
            part = ConversationParticipant(
                conversation_id=conv.id,
                user_id=current.id,
                last_read_message_id=last_msg_id,
                updated_at=datetime.utcnow(),
            )
            db.add(part)
            db.flush()

        last_msg = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(desc(Message.created_at))
            .first()
        )

        threshold = part.last_read_message_id or 0
        unread_count = (
            db.query(func.count(Message.id))
            .filter(Message.conversation_id == conv.id)
            .filter(Message.id > threshold)
            .filter(Message.sender_user_id.isnot(None))
            .filter(Message.sender_user_id != current.id)
            .scalar()
            or 0
        )

        post = db.get(InternshipPost, a.post_id)
        post_title = post.title if post else "Internship"

        # other party display name
        if current.role == UserRole.STUDENT:
            other_party = db.get(User, a.company_user_id)
            other_name = other_party.company_profile.company_name if other_party and other_party.company_profile and other_party.company_profile.company_name else (other_party.username if other_party else "Company")
        else:
            other_party = db.get(User, a.student_user_id)
            other_name = other_party.username if other_party else "Student"

        out.append(ApplicationListItem(
            applicationId=a.id,
            status=a.status,
            conversationId=conv.id,
            postId=a.post_id,
            postTitle=post_title,
            otherPartyName=other_name,
            lastMessage=last_msg.text if last_msg else None,
            unreadCount=int(unread_count),
            lastMessageId=last_msg.id if last_msg else None,
            lastMessageAt=last_msg.created_at if last_msg else None,
        ))

    db.commit()
    return out


@router.post("/{application_id}/status")
def set_application_status(
    application_id: int,
    req: SetApplicationStatusRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if current.role != UserRole.COMPANY or app.company_user_id != current.id:
        raise HTTPException(status_code=403, detail="Only the owning company can update status")

    # Some clients send LIKE/PASS; map to application statuses.
    if req.status == "LIKE":
        new_status = ApplicationStatus.ACCEPTED
    elif req.status == "PASS":
        new_status = ApplicationStatus.DECLINED
    else:
        new_status = ApplicationStatus(req.status)

    # If already that status, do nothing
    if app.status == new_status:
        return {"ok": True}

    app.status = new_status
    app.updated_at = datetime.utcnow()

    conv = db.query(Conversation).filter(Conversation.application_id == app.id).first()
    if not conv:
        raise HTTPException(status_code=500, detail="Conversation missing")

    system_text = status_to_system_text(new_status)
    db.add(Message(
        conversation_id=conv.id,
        type=MessageType.SYSTEM,
        sender_user_id=None,
        text=system_text,
    ))

    db.commit()
    return {"ok": True}
