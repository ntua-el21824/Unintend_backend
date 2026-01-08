from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..deps import get_db, get_current_user
from ..models import User, UserRole, StudentProfile, CompanyProfile, StudentProfilePost
from ..schemas import RegisterRequest, LoginRequest, TokenResponse, MeResponse, UpdateMeRequest
from ..auth import hash_password, verify_password, create_access_token
from ..url_utils import to_public_url

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(or_(User.username == req.username, User.email == req.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        surname=req.surname,
        role=req.role,
    )
    db.add(user)
    db.flush()

    # create empty profile row
    if req.role == UserRole.STUDENT:
        db.add(StudentProfile(user_id=user.id))
        # also create an initial profile "post" card for company feed
        db.flush()
        _ensure_student_profile_post(db, user)
    else:
        db.add(CompanyProfile(user_id=user.id))

    db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        or_(User.username == req.username_or_email, User.email == req.username_or_email)
    ).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(request: Request, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    bio = studies = experience = None
    company_name = company_bio = None
    if current.role == UserRole.STUDENT:
        sp = db.query(StudentProfile).filter(StudentProfile.user_id == current.id).first()
        if sp:
            bio = sp.bio
            studies = sp.studies
            experience = sp.experience
    else:
        cp = db.query(CompanyProfile).filter(CompanyProfile.user_id == current.id).first()
        if cp:
            company_name = cp.company_name
            company_bio = cp.bio or cp.description

    return MeResponse(
        id=current.id,
        username=current.username,
        email=current.email,
        name=current.name,
        surname=current.surname,
        role=current.role,
        profileImageUrl=to_public_url(current.profile_image_url, request),
        bio=bio,
        studies=studies,
        experience=experience,
        companyName=company_name,
        companyBio=company_bio,
    )


@router.put("/me", response_model=MeResponse)
def update_me(
    request: Request,
    req: UpdateMeRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if req.name is not None:
        current.name = req.name
    if req.surname is not None:
        current.surname = req.surname

    bio = studies = experience = None
    company_name = company_bio = None

    if current.role == UserRole.STUDENT:
        sp = db.query(StudentProfile).filter(StudentProfile.user_id == current.id).first()
        if not sp:
            sp = StudentProfile(user_id=current.id)
            db.add(sp)
            db.flush()

        if req.bio is not None:
            sp.bio = req.bio
        if req.studies is not None:
            sp.studies = req.studies
        if req.experience is not None:
            sp.experience = req.experience

        bio = sp.bio
        studies = sp.studies
        experience = sp.experience

        _ensure_student_profile_post(db, current, sp)
    else:
        # COMPANY
        cp = db.query(CompanyProfile).filter(CompanyProfile.user_id == current.id).first()
        if not cp:
            cp = CompanyProfile(user_id=current.id)
            db.add(cp)
            db.flush()

        if req.companyName is not None:
            cp.company_name = req.companyName
        if req.companyBio is not None:
            cp.bio = req.companyBio
            # keep description in sync for backward compatibility
            cp.description = req.companyBio

        company_name = cp.company_name
        company_bio = cp.bio or cp.description

    db.commit()
    db.refresh(current)

    return MeResponse(
        id=current.id,
        username=current.username,
        email=current.email,
        name=current.name,
        surname=current.surname,
        role=current.role,
        profileImageUrl=to_public_url(current.profile_image_url, request),
        bio=bio,
        studies=studies,
        experience=experience,
        companyName=company_name,
        companyBio=company_bio,
    )


# helpers
def _ensure_student_profile_post(db: Session, user: User, sp: StudentProfile | None = None):
    """Create or refresh the StudentProfilePost used in the company feed based on profile data."""
    if user.role != UserRole.STUDENT:
        return

    if sp is None:
        sp = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()

    title = "Student Profile"
    if sp and sp.studies:
        title = sp.studies
    elif user.name:
        title = f"{user.name} {user.surname or ''}".strip()

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

    description = "\n".join([part for part in desc_parts if part]) or "Student profile"

    spost = (
        db.query(StudentProfilePost)
        .filter(StudentProfilePost.student_user_id == user.id)
        .first()
    )
    if not spost:
        spost = StudentProfilePost(
            student_user_id=user.id,
            title=title,
            description=description,
            location=None,
            is_active=True,
        )
        db.add(spost)
    else:
        spost.title = title
        spost.description = description

    db.flush()
