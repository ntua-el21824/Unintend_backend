from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..models import User, UserRole, StudentProfile
from ..schemas import StudentPublicProfileResponse
from ..url_utils import to_public_url

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/students/{student_user_id}", response_model=StudentPublicProfileResponse)
def get_student_public_profile(
    student_user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    user = db.get(User, student_user_id)
    if not user or user.role != UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="Student not found")

    sp = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()

    return StudentPublicProfileResponse(
        id=user.id,
        username=user.username,
        name=user.name,
        surname=user.surname,
        profileImageUrl=to_public_url(user.profile_image_url, request),
        university=sp.university if sp else None,
        department=sp.department if sp else None,
        bio=sp.bio if sp else None,
        skills=sp.skills if sp else None,
        studies=sp.studies if sp else None,
        experience=sp.experience if sp else None,
    )
