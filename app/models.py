import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, UniqueConstraint, Enum
)
from sqlalchemy.orm import relationship

from .db import Base


class UserRole(str, enum.Enum):
    STUDENT = "STUDENT"
    COMPANY = "COMPANY"


class Decision(str, enum.Enum):
    NONE = "NONE"
    LIKE = "LIKE"
    PASS = "PASS"


class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class MessageType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    name = Column(String(80), nullable=True)
    surname = Column(String(80), nullable=True)

    profile_image_url = Column(Text, nullable=True)

    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_profile = relationship("StudentProfile", back_populates="user", uselist=False)
    company_profile = relationship("CompanyProfile", back_populates="user", uselist=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    university = Column(String(120), nullable=True)
    department = Column(String(120), nullable=True)
    bio = Column(Text, nullable=True)
    skills = Column(Text, nullable=True)  # comma-separated or JSON string
    studies = Column(Text, nullable=True)
    experience = Column(Text, nullable=True)

    user = relationship("User", back_populates="student_profile")


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    company_name = Column(String(120), nullable=True)
    industry = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)
    website = Column(String(200), nullable=True)
    bio = Column(Text, nullable=True)

    user = relationship("User", back_populates="company_profile")


# ============================================================
# POSTS
# ============================================================

class InternshipPost(Base):
    __tablename__ = "internship_posts"

    id = Column(Integer, primary_key=True)
    company_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(120), nullable=True)

    department = Column(String(120), nullable=True)

    image_url = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    company_user = relationship("User")


class StudentProfilePost(Base):
    """
    Αυτό είναι το "post" που βλέπει η εταιρία στο feed της:
    μια περιγραφή/κάρτα του προφίλ του φοιτητή (σαν post).
    """
    __tablename__ = "student_profile_posts"

    id = Column(Integer, primary_key=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(120), nullable=True)      # π.χ. "CS Student - 3rd year"
    description = Column(Text, nullable=False)      # bio/skills/summary
    location = Column(String(120), nullable=True)

    image_url = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_user = relationship("User")


class StudentExperiencePost(Base):
    """
    Student-only posts that live on the student's profile (seminars, experiences, etc.).
    These do NOT appear in company feed; they are for the student's own profile page.
    """
    __tablename__ = "student_experience_posts"

    id = Column(Integer, primary_key=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(80), nullable=True)

    image_url = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_user = relationship("User")


# ============================================================
# INTERACTIONS (Tinder-like)
# ============================================================

class StudentPostInteraction(Base):
    """
    Student -> InternshipPost interactions (LIKE/PASS/SAVE)
    """
    __tablename__ = "student_post_interactions"
    __table_args__ = (
        UniqueConstraint("student_user_id", "post_id", name="uq_student_post"),
    )

    id = Column(Integer, primary_key=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    post_id = Column(Integer, ForeignKey("internship_posts.id"), nullable=False, index=True)

    saved = Column(Boolean, default=False, nullable=False)
    decision = Column(Enum(Decision), default=Decision.NONE, nullable=False)

    saved_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)

    student_user = relationship("User")
    post = relationship("InternshipPost")


class CompanyStudentPostInteraction(Base):
    """
    Company -> StudentProfilePost interactions (LIKE/PASS/SAVE)
    Η εταιρία κάνει like/pass/save σε "post" φοιτητή (όχι σε user γενικά).
    """
    __tablename__ = "company_student_post_interactions"
    __table_args__ = (
        UniqueConstraint("company_user_id", "student_post_id", name="uq_company_student_post"),
    )

    id = Column(Integer, primary_key=True)
    company_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_post_id = Column(Integer, ForeignKey("student_profile_posts.id"), nullable=False, index=True)

    saved = Column(Boolean, default=False, nullable=False)
    decision = Column(Enum(Decision), default=Decision.NONE, nullable=False)

    saved_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)

    company_user = relationship("User", foreign_keys=[company_user_id])
    student_post = relationship("StudentProfilePost")


# ============================================================
# APPLICATIONS + CHAT
# ============================================================

class Application(Base):
    """
    Δημιουργείται όταν student κάνει LIKE σε post.
    Από εδώ βγαίνει το status (pending/accepted/declined) και "δένει" το chat.
    """
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("post_id", "student_user_id", name="uq_post_student_application"),
    )

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("internship_posts.id"), nullable=False, index=True)
    student_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("InternshipPost")
    student_user = relationship("User", foreign_keys=[student_user_id])
    company_user = relationship("User", foreign_keys=[company_user_id])

    conversation = relationship("Conversation", back_populates="application", uselist=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), unique=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    application = relationship("Application", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")

    participants = relationship("ConversationParticipant", back_populates="conversation")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_user"),
    )

    id = Column(Integer, primary_key=True)

    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Unread calculation uses: messages.id > last_read_message_id AND sender_user_id != user_id
    last_read_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)

    type = Column(Enum(MessageType), default=MessageType.USER, nullable=False)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    sender_user = relationship("User")
