from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import asc

from ..deps import get_db, get_current_user
from ..models import Conversation, Message, MessageType, Application, UserRole, ApplicationStatus
from ..schemas import MessageResponse, SendMessageRequest

router = APIRouter(prefix="/conversations", tags=["chat"])


def can_access_conversation(db: Session, conv_id: int, user_id: int) -> bool:
    conv = db.get(Conversation, conv_id)
    if not conv:
        return False
    app = db.get(Application, conv.application_id)
    if not app:
        return False
    return app.student_user_id == user_id or app.company_user_id == user_id


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
    db.commit()
    db.refresh(msg)
    return _message_to_response(msg, app)


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
