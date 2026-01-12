from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import asc, func
from datetime import datetime

from ..deps import get_db, get_current_user
from ..models import Conversation, Message, MessageType, Application, UserRole, ApplicationStatus, ConversationParticipant
from ..schemas import MessageResponse, SendMessageRequest, MarkConversationReadRequest, MarkConversationReadResponse

router = APIRouter(prefix="/conversations", tags=["chat"])


def can_access_conversation(db: Session, conv_id: int, user_id: int) -> bool:
    conv = db.get(Conversation, conv_id)
    if not conv:
        return False
    app = db.get(Application, conv.application_id)
    if not app:
        return False
    return app.student_user_id == user_id or app.company_user_id == user_id


def _ensure_participant(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    seed_last_read_to_last_message: bool,
) -> ConversationParticipant:
    row = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if row:
        return row

    last_msg_id = None
    if seed_last_read_to_last_message:
        last_msg_id = (
            db.query(func.max(Message.id))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        )

    row = ConversationParticipant(
        conversation_id=conversation_id,
        user_id=user_id,
        last_read_message_id=last_msg_id,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _unread_count(db: Session, *, conversation_id: int, user_id: int, last_read_message_id: int | None) -> int:
    threshold = last_read_message_id or 0
    return (
        db.query(func.count(Message.id))
        .filter(Message.conversation_id == conversation_id)
        .filter(Message.id > threshold)
        .filter(Message.sender_user_id.isnot(None))
        .filter(Message.sender_user_id != user_id)
        .scalar()
        or 0
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if not can_access_conversation(db, conversation_id, current.id):
        raise HTTPException(status_code=403, detail="No access")

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(asc(Message.created_at))
        .all()
    )
    app = db.get(Application, db.get(Conversation, conversation_id).application_id)

    return [_message_to_response(m, app) for m in msgs]


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
def send_message(
    conversation_id: int,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    app = db.get(Application, conv.application_id)
    if not app:
        raise HTTPException(status_code=500, detail="Application missing")

    if not (app.student_user_id == current.id or app.company_user_id == current.id):
        raise HTTPException(status_code=403, detail="No access")

    # Optional rule: block chat if declined
    if app.status == ApplicationStatus.DECLINED:
        raise HTTPException(status_code=400, detail="Conversation declined")

    msg = Message(
        conversation_id=conversation_id,
        type=MessageType.USER,
        sender_user_id=current.id,
        text=req.text,
    )
    db.add(msg)

    # Ensure participant rows exist (backfill) and mark sender as having read up to their own message.
    _ensure_participant(db, conversation_id=conversation_id, user_id=current.id, seed_last_read_to_last_message=True)
    app_other_id = app.company_user_id if app.student_user_id == current.id else app.student_user_id
    _ensure_participant(db, conversation_id=conversation_id, user_id=app_other_id, seed_last_read_to_last_message=True)

    db.flush()  # populate msg.id

    sender_part = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current.id,
        )
        .first()
    )
    if sender_part:
        sender_part.last_read_message_id = msg.id
        sender_part.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(msg)
    return _message_to_response(msg, app)


@router.post("/{conversation_id}/read", response_model=MarkConversationReadResponse)
def mark_conversation_read(
    conversation_id: int,
    req: MarkConversationReadRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    if not can_access_conversation(db, conversation_id, current.id):
        raise HTTPException(status_code=403, detail="No access")

    # Backfill participant row for existing conversations. We DO NOT auto-seed to last message here,
    # because this endpoint is called when the user actually opens the chat.
    part = _ensure_participant(db, conversation_id=conversation_id, user_id=current.id, seed_last_read_to_last_message=False)

    target_id = None
    if req.lastReadMessageId is not None:
        m = db.get(Message, req.lastReadMessageId)
        if not m or m.conversation_id != conversation_id:
            raise HTTPException(status_code=400, detail="Invalid lastReadMessageId")
        target_id = m.id
    else:
        target_id = (
            db.query(func.max(Message.id))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        )

    # If there are no messages yet, keep last_read_message_id as-is.
    if target_id is not None:
        part.last_read_message_id = target_id
        part.updated_at = datetime.utcnow()

    db.commit()

    return MarkConversationReadResponse(
        conversationId=conversation_id,
        unreadCount=0,
        lastReadMessageId=part.last_read_message_id,
    )


def _message_to_response(m: Message, app: Application) -> MessageResponse:
    sender_role = None
    if m.sender_user_id is None:
        sender_role = None
    elif m.sender_user_id == app.company_user_id:
        sender_role = UserRole.COMPANY
    elif m.sender_user_id == app.student_user_id:
        sender_role = UserRole.STUDENT

    return MessageResponse(
        id=m.id,
        type=m.type,
        senderUserId=m.sender_user_id,
        text=m.text,
        createdAt=m.created_at,
        fromCompany=(sender_role == UserRole.COMPANY),
        isSystem=(m.type == MessageType.SYSTEM),
    )
