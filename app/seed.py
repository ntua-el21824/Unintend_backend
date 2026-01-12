from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from .db import SessionLocal, engine, Base
from .models import (
    User, UserRole, StudentProfile, CompanyProfile,
    InternshipPost, StudentPostInteraction, Decision,
    Application, ApplicationStatus, Conversation, Message, MessageType,
    StudentProfilePost, StudentExperiencePost,
    CompanyStudentPostInteraction,
)
from .auth import hash_password
from .migrations import ensure_sqlite_columns

PENDING_TEXT = "Message still pending"
ACCEPTED_TEXT = "Ready to connect?"
DECLINED_TEXT = "Unfortunately this was not a match, keep searching!"


ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _uploads_root() -> Path:
    # workspace-root/uploads
    return Path(__file__).resolve().parents[1] / "uploads"


def _find_upload_url(*, subdir: str, stem: str) -> str | None:
    """Find an existing image under uploads/<subdir>/<stem>.<ext> and return /uploads/... URL."""
    root = _uploads_root() / subdir
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        candidate = root / f"{stem}{ext}"
        if candidate.exists():
            return f"/uploads/{subdir}/{candidate.name}"
    return None


_SKIP_PROFILE_IMAGE_USERNAMES = {"eleni"}


def _maybe_update(model_obj, **fields):
    changed = False
    for key, value in fields.items():
        if getattr(model_obj, key) != value:
            setattr(model_obj, key, value)
            changed = True
    return changed


def get_or_create_user(db: Session, *, username: str, email: str, password: str, role: UserRole, name: str, surname: str):
    u = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if u:
        return u
    u = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        name=name,
        surname=surname,
    )
    db.add(u)
    db.flush()
    return u


def ensure_student_profile(
    db: Session,
    user_id: int,
    university: str,
    department: str,
    bio: str,
    skills: str,
    studies: str | None = None,
    experience: str | None = None,
):
    sp = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if sp:
        return sp
    sp = StudentProfile(
        user_id=user_id,
        university=university,
        department=department,
        bio=bio,
        skills=skills,
        studies=studies,
        experience=experience,
    )
    db.add(sp)
    db.flush()
    return sp


def ensure_company_profile(db: Session, user_id: int, company_name: str, industry: str, description: str, website: str):
    cp = db.query(CompanyProfile).filter(CompanyProfile.user_id == user_id).first()
    if cp:
        return cp
    cp = CompanyProfile(
        user_id=user_id,
        company_name=company_name,
        industry=industry,
        description=description,
        website=website,
    )
    db.add(cp)
    db.flush()
    return cp


def create_post(db: Session, company_user_id: int, title: str, description: str, location: str):
    p = db.query(InternshipPost).filter(
        InternshipPost.company_user_id == company_user_id,
        InternshipPost.title == title,
    ).first()
    if p:
        _maybe_update(p, description=description, location=location, is_active=True)
        return p
    p = InternshipPost(
        company_user_id=company_user_id,
        title=title,
        description=description,
        location=location,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(p)
    db.flush()
    return p


def create_student_profile_post(db: Session, student_user_id: int, title: str, description: str, location: str):
    p = db.query(StudentProfilePost).filter(StudentProfilePost.student_user_id == student_user_id).first()
    if p:
        _maybe_update(p, title=title, description=description, location=location, is_active=True)
        return p
    p = StudentProfilePost(
        student_user_id=student_user_id,
        title=title,
        description=description,
        location=location,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(p)
    db.flush()
    return p


def ensure_student_experience_post(db: Session, *, student_user_id: int, title: str, description: str, category: str | None):
    p = db.query(StudentExperiencePost).filter(
        StudentExperiencePost.student_user_id == student_user_id,
        StudentExperiencePost.title == title,
    ).first()
    if p:
        _maybe_update(p, description=description, category=category, is_active=True)
        return p
    p = StudentExperiencePost(
        student_user_id=student_user_id,
        title=title,
        description=description,
        category=category,
        created_at=datetime.utcnow(),
    )
    db.add(p)
    db.flush()
    return p


def ensure_student_post_interaction(
    db: Session,
    *,
    student_user_id: int,
    post_id: int,
    saved: bool,
    decision: Decision,
    saved_at: datetime | None,
    decided_at: datetime | None,
):
    inter = db.query(StudentPostInteraction).filter(
        StudentPostInteraction.student_user_id == student_user_id,
        StudentPostInteraction.post_id == post_id,
    ).first()
    if not inter:
        inter = StudentPostInteraction(
            student_user_id=student_user_id,
            post_id=post_id,
            saved=saved,
            decision=decision,
            saved_at=saved_at,
            decided_at=decided_at,
        )
        db.add(inter)
        db.flush()
        return inter

    inter.saved = saved
    inter.decision = decision
    inter.saved_at = saved_at
    inter.decided_at = decided_at
    return inter


def ensure_company_student_post_interaction(
    db: Session,
    *,
    company_user_id: int,
    student_post_id: int,
    saved: bool,
    decision: Decision,
    saved_at: datetime | None,
    decided_at: datetime | None,
):
    inter = db.query(CompanyStudentPostInteraction).filter(
        CompanyStudentPostInteraction.company_user_id == company_user_id,
        CompanyStudentPostInteraction.student_post_id == student_post_id,
    ).first()
    if not inter:
        inter = CompanyStudentPostInteraction(
            company_user_id=company_user_id,
            student_post_id=student_post_id,
            saved=saved,
            decision=decision,
            saved_at=saved_at,
            decided_at=decided_at,
        )
        db.add(inter)
        db.flush()
        return inter

    inter.saved = saved
    inter.decision = decision
    inter.saved_at = saved_at
    inter.decided_at = decided_at
    return inter


def ensure_application_with_conversation(db: Session, *, post_id: int, student_user_id: int, company_user_id: int, status: ApplicationStatus):
    app = db.query(Application).filter(Application.post_id == post_id, Application.student_user_id == student_user_id).first()
    if not app:
        app = Application(
            post_id=post_id,
            student_user_id=student_user_id,
            company_user_id=company_user_id,
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(app)
        db.flush()
    else:
        app.status = status
        app.updated_at = datetime.utcnow()

    conv = db.query(Conversation).filter(Conversation.application_id == app.id).first()
    if not conv:
        conv = Conversation(application_id=app.id)
        db.add(conv)
        db.flush()

    system_text = (
        PENDING_TEXT if status == ApplicationStatus.PENDING
        else ACCEPTED_TEXT if status == ApplicationStatus.ACCEPTED
        else DECLINED_TEXT
    )

    # Avoid endless duplicate system messages when re-running the seed.
    existing_system = db.query(Message).filter(
        Message.conversation_id == conv.id,
        Message.type == MessageType.SYSTEM,
        Message.sender_user_id.is_(None),
        Message.text == system_text,
    ).first()
    if not existing_system:
        db.add(Message(
            conversation_id=conv.id,
            type=MessageType.SYSTEM,
            sender_user_id=None,
            text=system_text
        ))
        db.flush()

    return app, conv


def main():
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns(engine)

    db = SessionLocal()
    try:
        # --- Companies ---
        company_specs = [
            {
                "username": "acme_hr",
                "email": "hr@acme.com",
                "name": "ACME",
                "surname": "HR",
                "company_name": "ACME Labs",
                "industry": "Software",
                "description": "We build cool products. Looking for interns in mobile/backend.",
                "website": "https://acme.example",
            },
            {
                "username": "green_energy",
                "email": "jobs@greenenergy.com",
                "name": "Green",
                "surname": "Energy",
                "company_name": "GreenEnergy",
                "industry": "Energy",
                "description": "Sustainability & data. Interns welcome!",
                "website": "https://greenenergy.example",
            },
            {
                "username": "medix_talent",
                "email": "careers@medixhealth.com",
                "name": "Medix",
                "surname": "Talent",
                "company_name": "MedixHealth",
                "industry": "HealthTech",
                "description": "Digital health products. Interns for backend/data/QA.",
                "website": "https://medixhealth.example",
            },
            {
                "username": "finwave_jobs",
                "email": "jobs@finwave.io",
                "name": "Finwave",
                "surname": "Jobs",
                "company_name": "Finwave",
                "industry": "FinTech",
                "description": "Payments & risk. Looking for SWE and data interns.",
                "website": "https://finwave.example",
            },
            {
                "username": "logi_chain",
                "email": "hr@logichain.com",
                "name": "Logi",
                "surname": "Chain",
                "company_name": "LogiChain",
                "industry": "Logistics",
                "description": "Routing, delivery ops and dashboards. Interns welcome.",
                "website": "https://logichain.example",
            },
            {
                "username": "aero_ai",
                "email": "jobs@aeroai.com",
                "name": "Aero",
                "surname": "AI",
                "company_name": "AeroAI",
                "industry": "AI / Robotics",
                "description": "Computer vision & edge ML. Interns for Python/CV/ML.",
                "website": "https://aeroai.example",
            },
            {
                "username": "campus_cafe",
                "email": "hr@campuscafe.gr",
                "name": "Campus",
                "surname": "Cafe",
                "company_name": "CampusCafe",
                "industry": "FoodTech",
                "description": "Ordering & loyalty platform for students. Web/mobile interns.",
                "website": "https://campuscafe.example",
            },
            {
                "username": "blue_marine",
                "email": "careers@bluemarine.com",
                "name": "Blue",
                "surname": "Marine",
                "company_name": "BlueMarine",
                "industry": "Maritime",
                "description": "Fleet operations software. Interns for data and backend.",
                "website": "https://bluemarine.example",
            },
            {
                "username": "agrobyte",
                "email": "jobs@agrobyte.io",
                "name": "Agro",
                "surname": "Byte",
                "company_name": "AgroByte",
                "industry": "AgriTech",
                "description": "IoT + analytics for farms. Interns for ETL/dashboards.",
                "website": "https://agrobyte.example",
            },
            {
                "username": "civic_soft",
                "email": "jobs@civicsoft.org",
                "name": "Civic",
                "surname": "Soft",
                "company_name": "CivicSoft",
                "industry": "GovTech",
                "description": "Open-data platforms for municipalities. Interns for fullstack.",
                "website": "https://civicsoft.example",
            },
        ]

        companies: dict[str, User] = {}
        for spec in company_specs:
            cu = get_or_create_user(
                db,
                username=spec["username"],
                email=spec["email"],
                password="pass1234",
                role=UserRole.COMPANY,
                name=spec["name"],
                surname=spec["surname"],
            )

            # Optional: set profile image if a matching file exists in uploads/profiles/
            existing_profile_url = _find_upload_url(subdir="profiles", stem=spec["username"])
            if existing_profile_url and cu.profile_image_url != existing_profile_url:
                cu.profile_image_url = existing_profile_url

            ensure_company_profile(
                db,
                user_id=cu.id,
                company_name=spec["company_name"],
                industry=spec["industry"],
                description=spec["description"],
                website=spec["website"],
            )
            companies[spec["username"]] = cu

        c1 = companies["acme_hr"]
        c2 = companies["green_energy"]

        # --- Students ---
        student_specs = [
            {
                "username": "eleni",
                "email": "eleni@student.com",
                "name": "Eleni",
                "surname": "Papadopoulou",
                "university": "AUEB",
                "department": "Informatics",
                "bio": "Interested in Flutter and backend development.",
                "skills": "Flutter,Dart,Python,SQL",
                "studies": "BSc Informatics - 3rd year",
                "experience": "Volunteer dev at uni club; small freelance landing pages",
                "location": "Athens",
                "post_title": "Flutter & Backend Intern",
            },
            {
                "username": "nikos",
                "email": "nikos@student.com",
                "name": "Nikos",
                "surname": "Ioannou",
                "university": "NTUA",
                "department": "ECE",
                "bio": "Looking for an internship in data/ML.",
                "skills": "Python,Machine Learning,Pandas,SQL",
                "studies": "Diploma Thesis on time-series forecasting",
                "experience": "Teaching assistant; Kaggle bronze; part-time data cleaning",
                "location": "Athens / Remote",
                "post_title": "Data / ML Intern",
            },
            {
                "username": "maria",
                "email": "maria@student.com",
                "name": "Maria",
                "surname": "Kostopoulou",
                "university": "AUTH",
                "department": "Computer Science",
                "bio": "Frontend-oriented, strong in UX and accessibility.",
                "skills": "React,TypeScript,HTML,CSS,Accessibility",
                "studies": "BSc CS - 4th year",
                "experience": "Interned at a local agency; built component libraries",
                "location": "Thessaloniki",
                "post_title": "Frontend Intern (React/TS)",
            },
            {
                "username": "giorgos",
                "email": "giorgos@student.com",
                "name": "Giorgos",
                "surname": "Nikolaidis",
                "university": "University of Patras",
                "department": "Computer Engineering",
                "bio": "Backend + systems. Enjoys APIs, databases, and performance.",
                "skills": "Python,FastAPI,PostgreSQL,Docker,Redis",
                "studies": "BSc CE - final year",
                "experience": "Built REST APIs; deployment with Docker; basic observability",
                "location": "Patras / Remote",
                "post_title": "Backend Intern (APIs & DB)",
            },
            {
                "username": "sofia",
                "email": "sofia@student.com",
                "name": "Sofia",
                "surname": "Tzima",
                "university": "Panteion",
                "department": "Applied Informatics",
                "bio": "Product-minded; likes analytics and experimentation.",
                "skills": "SQL,Python,Tableau,Product Analytics,A/B Testing",
                "studies": "BSc Applied Informatics - 2nd year",
                "experience": "University project: analytics for student platform",
                "location": "Athens",
                "post_title": "Analytics / BI Intern",
            },
            {
                "username": "kostas",
                "email": "kostas@student.com",
                "name": "Kostas",
                "surname": "Zafeiris",
                "university": "HUA",
                "department": "Informatics",
                "bio": "QA-minded developer; enjoys automation and clean test suites.",
                "skills": "Python,Pytest,Playwright,CI/CD,Git",
                "studies": "BSc Informatics - 3rd year",
                "experience": "Wrote E2E tests for a club project; improved flaky tests",
                "location": "Athens / Remote",
                "post_title": "QA / Automation Intern",
            },
            {
                "username": "anna",
                "email": "anna@student.com",
                "name": "Anna",
                "surname": "Karamani",
                "university": "UoM",
                "department": "Information Systems",
                "bio": "Fullstack student, likes clean APIs and UI polish.",
                "skills": "Node.js,React,TypeScript,SQL,REST",
                "studies": "BSc IS - 3rd year",
                "experience": "Built a small marketplace app; worked with auth and payments sandbox",
                "location": "Thessaloniki / Remote",
                "post_title": "Fullstack Intern (React/Node)",
            },
            {
                "username": "dimitris",
                "email": "dimitris@student.com",
                "name": "Dimitris",
                "surname": "Koutsou",
                "university": "IONIO",
                "department": "Informatics",
                "bio": "Cybersecurity-curious; enjoys threat modeling and secure coding.",
                "skills": "Python,Security,OWASP,Burp Suite,Networking",
                "studies": "BSc Informatics - 4th year",
                "experience": "CTF participant; wrote a small static analyzer for Python",
                "location": "Corfu / Remote",
                "post_title": "Security / Backend Intern",
            },
            {
                "username": "irene",
                "email": "irene@student.com",
                "name": "Irene",
                "surname": "Manou",
                "university": "AUEB",
                "department": "Statistics",
                "bio": "Data-first; interested in BI and applied ML.",
                "skills": "Python,SQL,Statistics,Power BI,Scikit-learn",
                "studies": "BSc Statistics - 3rd year",
                "experience": "Dashboarded student survey results; basic churn modeling",
                "location": "Athens",
                "post_title": "Data / BI Intern",
            },
            {
                "username": "petros",
                "email": "petros@student.com",
                "name": "Petros",
                "surname": "Stavrou",
                "university": "NTUA",
                "department": "Mechanical Eng (Computing track)",
                "bio": "Interested in robotics software and simulation.",
                "skills": "Python,C++,ROS,Simulation,Gazebo",
                "studies": "Diploma - 4th year",
                "experience": "Robot navigation project; implemented sensors + basic SLAM pipeline",
                "location": "Athens",
                "post_title": "Robotics / ML Intern",
            },
        ]

        students: dict[str, tuple[User, StudentProfile, StudentProfilePost]] = {}
        for spec in student_specs:
            su = get_or_create_user(
                db,
                username=spec["username"],
                email=spec["email"],
                password="pass1234",
                role=UserRole.STUDENT,
                name=spec["name"],
                surname=spec["surname"],
            )

            # Optional: set profile image if a matching file exists in uploads/profiles/
            if spec["username"] not in _SKIP_PROFILE_IMAGE_USERNAMES:
                existing_profile_url = _find_upload_url(subdir="profiles", stem=spec["username"])
                if existing_profile_url and su.profile_image_url != existing_profile_url:
                    su.profile_image_url = existing_profile_url

            sp = ensure_student_profile(
                db,
                user_id=su.id,
                university=spec["university"],
                department=spec["department"],
                bio=spec["bio"],
                skills=spec["skills"],
                studies=spec["studies"],
                experience=spec["experience"],
            )
            stpost = create_student_profile_post(
                db,
                student_user_id=su.id,
                title=spec["post_title"],
                description=(
                    f"{sp.bio}\n"
                    f"Skills: {sp.skills}\n"
                    f"Studies: {sp.studies}\n"
                    f"Experience: {sp.experience}\n"
                    f"University: {sp.university} ({sp.department})"
                ),
                location=spec["location"],
            )

            # Optional: set student profile-post image if present in uploads/student-profile-posts/
            existing_student_post_url = _find_upload_url(subdir="student-profile-posts", stem=str(stpost.id))
            if existing_student_post_url and stpost.image_url != existing_student_post_url:
                stpost.image_url = existing_student_post_url

            students[spec["username"]] = (su, sp, stpost)

        s1, sp1, stpost1 = students["eleni"]
        s2, sp2, stpost2 = students["nikos"]

        # --- Student profile-only posts (seminars/experiences) ---
        ensure_student_experience_post(
            db,
            student_user_id=s1.id,
            title="Attended Flutter Europe",
            description="Talks on state management and testing",
            category="seminar",
        )
        ensure_student_experience_post(
            db,
            student_user_id=s2.id,
            title="Research assistant - time series",
            description="Implemented LSTM and Prophet baselines for energy dataset",
            category="experience",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["maria"][0].id,
            title="Hackathon: accessibility-first UI",
            description="Built a React UI with keyboard navigation and ARIA best practices",
            category="seminar",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["giorgos"][0].id,
            title="Dockerized a FastAPI service",
            description="Added health checks, env configs, and basic logs for a uni project",
            category="experience",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["sofia"][0].id,
            title="Tableau workshop",
            description="Dashboards, calculated fields, and storytelling with data",
            category="seminar",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["kostas"][0].id,
            title="Automated tests with Playwright",
            description="Wrote smoke tests and stabilized CI pipeline for a small app",
            category="experience",
        )

        ensure_student_experience_post(
            db,
            student_user_id=students["anna"][0].id,
            title="Built a fullstack side project",
            description="React frontend + simple API; learned pagination, forms and auth flows",
            category="experience",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["dimitris"][0].id,
            title="OWASP Top 10 study group",
            description="Reviewed common web vulnerabilities and mitigations with examples",
            category="seminar",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["irene"][0].id,
            title="Power BI workshop",
            description="Data modeling, DAX basics, and KPI dashboards",
            category="seminar",
        )
        ensure_student_experience_post(
            db,
            student_user_id=students["petros"][0].id,
            title="Robotics lab project",
            description="Simulated a robot and implemented a basic controller in Python",
            category="experience",
        )

        # --- Internship Posts (company -> student feed) ---
        p1 = create_post(
            db,
            company_user_id=c1.id,
            title="Flutter Intern",
            description="Help us build a mobile app. Nice-to-have: REST APIs, Firebase.",
            location="Athens / Hybrid"
        )
        p2 = create_post(
            db,
            company_user_id=c1.id,
            title="Backend Intern (FastAPI)",
            description="Work with FastAPI + SQLite/Postgres. Learn auth, APIs, testing.",
            location="Remote"
        )
        p3 = create_post(
            db,
            company_user_id=c2.id,
            title="Data Intern",
            description="Data cleaning and dashboards. Python required.",
            location="Athens"
        )

        p4 = create_post(
            db,
            company_user_id=companies["medix_talent"].id,
            title="QA / Automation Intern",
            description="Write automated tests and help us improve release quality.",
            location="Athens / Remote",
        )
        p5 = create_post(
            db,
            company_user_id=companies["finwave_jobs"].id,
            title="Backend Intern (Payments)",
            description="APIs, integrations and database work. Interest in security is a plus.",
            location="Remote",
        )
        p6 = create_post(
            db,
            company_user_id=companies["logi_chain"].id,
            title="Frontend Intern (Dashboard)",
            description="Build internal dashboards. React/TypeScript preferred.",
            location="Thessaloniki / Hybrid",
        )

        p7 = create_post(
            db,
            company_user_id=companies["aero_ai"].id,
            title="Computer Vision Intern",
            description="Work on image datasets and model evaluation. Python required.",
            location="Athens / Hybrid",
        )
        p8 = create_post(
            db,
            company_user_id=companies["campus_cafe"].id,
            title="Mobile Intern",
            description="Help build a student-facing app. Interest in Flutter/React Native is a plus.",
            location="Athens",
        )
        p9 = create_post(
            db,
            company_user_id=companies["blue_marine"].id,
            title="Data Intern (Operations)",
            description="Dashboards and ETL for fleet KPIs. SQL + Python.",
            location="Piraeus / Hybrid",
        )
        p10 = create_post(
            db,
            company_user_id=companies["civic_soft"].id,
            title="Fullstack Intern",
            description="APIs + frontend features for open-data portals. Any modern stack welcome.",
            location="Remote",
        )

        # Optional: set internship post images if present in uploads/internship-posts/<post_id>.<ext>
        for p in (p1, p2, p3, p4, p5, p6, p7, p8, p9, p10):
            existing_post_url = _find_upload_url(subdir="internship-posts", stem=str(p.id))
            if existing_post_url and p.image_url != existing_post_url:
                p.image_url = existing_post_url

        # --- Interactions (student side) ---
        ensure_student_post_interaction(
            db,
            student_user_id=s1.id,
            post_id=p3.id,
            saved=True,
            decision=Decision.NONE,
            saved_at=datetime.utcnow(),
            decided_at=None,
        )

        ensure_student_post_interaction(
            db,
            student_user_id=s2.id,
            post_id=p3.id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p3.id,
            student_user_id=s2.id,
            company_user_id=c2.id,
            status=ApplicationStatus.PENDING
        )

        ensure_student_post_interaction(
            db,
            student_user_id=s1.id,
            post_id=p1.id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        app, conv = ensure_application_with_conversation(
            db,
            post_id=p1.id,
            student_user_id=s1.id,
            company_user_id=c1.id,
            status=ApplicationStatus.ACCEPTED
        )

        # Avoid duplicates on re-run
        if not db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.type == MessageType.USER,
            Message.sender_user_id == c1.id,
            Message.text == "Καλησπέρα! Μπορείς να μας στείλεις το βιογραφικό σου?",
        ).first():
            db.add(Message(
                conversation_id=conv.id,
                type=MessageType.USER,
                sender_user_id=c1.id,
                text="Καλησπέρα! Μπορείς να μας στείλεις το βιογραφικό σου?",
            ))
        if not db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.type == MessageType.USER,
            Message.sender_user_id == s1.id,
            Message.text == "Καλησπέρα σας, σας επισυνάπτω τώρα το βιογραφικό μου.",
        ).first():
            db.add(Message(
                conversation_id=conv.id,
                type=MessageType.USER,
                sender_user_id=s1.id,
                text="Καλησπέρα σας, σας επισυνάπτω τώρα το βιογραφικό μου.",
            ))

        # --- Company interactions demo (company saves + likes student posts) ---
        ensure_company_student_post_interaction(
            db,
            company_user_id=c1.id,
            student_post_id=stpost2.id,
            saved=True,
            decision=Decision.NONE,
            saved_at=datetime.utcnow(),
            decided_at=None,
        )

        ensure_company_student_post_interaction(
            db,
            company_user_id=c2.id,
            student_post_id=stpost1.id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )

        # --- More interaction variety ---
        maria_u = students["maria"][0]
        giorgos_u = students["giorgos"][0]
        sofia_u = students["sofia"][0]
        kostas_u = students["kostas"][0]
        anna_u = students["anna"][0]
        dimitris_u = students["dimitris"][0]
        irene_u = students["irene"][0]
        petros_u = students["petros"][0]

        # Students browsing internship posts
        ensure_student_post_interaction(
            db,
            student_user_id=maria_u.id,
            post_id=p6.id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p6.id,
            student_user_id=maria_u.id,
            company_user_id=companies["logi_chain"].id,
            status=ApplicationStatus.PENDING,
        )

        ensure_student_post_interaction(
            db,
            student_user_id=giorgos_u.id,
            post_id=p2.id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p2.id,
            student_user_id=giorgos_u.id,
            company_user_id=c1.id,
            status=ApplicationStatus.DECLINED,
        )

        ensure_student_post_interaction(
            db,
            student_user_id=sofia_u.id,
            post_id=p3.id,
            saved=True,
            decision=Decision.PASS,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )

        ensure_student_post_interaction(
            db,
            student_user_id=kostas_u.id,
            post_id=p4.id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )
        app2, conv2 = ensure_application_with_conversation(
            db,
            post_id=p4.id,
            student_user_id=kostas_u.id,
            company_user_id=companies["medix_talent"].id,
            status=ApplicationStatus.ACCEPTED,
        )
        if not db.query(Message).filter(
            Message.conversation_id == conv2.id,
            Message.type == MessageType.USER,
            Message.sender_user_id == companies["medix_talent"].id,
            Message.text == "Hi Kostas! Quick call this week?",
        ).first():
            db.add(Message(
                conversation_id=conv2.id,
                type=MessageType.USER,
                sender_user_id=companies["medix_talent"].id,
                text="Hi Kostas! Quick call this week?",
            ))
        if not db.query(Message).filter(
            Message.conversation_id == conv2.id,
            Message.type == MessageType.USER,
            Message.sender_user_id == kostas_u.id,
            Message.text == "Yes, available Wed/Thu after 17:00.",
        ).first():
            db.add(Message(
                conversation_id=conv2.id,
                type=MessageType.USER,
                sender_user_id=kostas_u.id,
                text="Yes, available Wed/Thu after 17:00.",
            ))

        # Companies browsing student profile posts
        ensure_company_student_post_interaction(
            db,
            company_user_id=companies["finwave_jobs"].id,
            student_post_id=students["giorgos"][2].id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        ensure_company_student_post_interaction(
            db,
            company_user_id=companies["logi_chain"].id,
            student_post_id=students["maria"][2].id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )
        ensure_company_student_post_interaction(
            db,
            company_user_id=companies["medix_talent"].id,
            student_post_id=students["sofia"][2].id,
            saved=True,
            decision=Decision.NONE,
            saved_at=datetime.utcnow(),
            decided_at=None,
        )

        # A few interactions for the extra students/companies
        ensure_student_post_interaction(
            db,
            student_user_id=anna_u.id,
            post_id=p8.id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p8.id,
            student_user_id=anna_u.id,
            company_user_id=companies["campus_cafe"].id,
            status=ApplicationStatus.PENDING,
        )

        ensure_student_post_interaction(
            db,
            student_user_id=dimitris_u.id,
            post_id=p5.id,
            saved=False,
            decision=Decision.PASS,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )

        ensure_student_post_interaction(
            db,
            student_user_id=irene_u.id,
            post_id=p9.id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p9.id,
            student_user_id=irene_u.id,
            company_user_id=companies["blue_marine"].id,
            status=ApplicationStatus.ACCEPTED,
        )

        ensure_student_post_interaction(
            db,
            student_user_id=petros_u.id,
            post_id=p7.id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )
        ensure_application_with_conversation(
            db,
            post_id=p7.id,
            student_user_id=petros_u.id,
            company_user_id=companies["aero_ai"].id,
            status=ApplicationStatus.PENDING,
        )

        ensure_company_student_post_interaction(
            db,
            company_user_id=companies["civic_soft"].id,
            student_post_id=students["anna"][2].id,
            saved=True,
            decision=Decision.LIKE,
            saved_at=datetime.utcnow(),
            decided_at=datetime.utcnow(),
        )
        ensure_company_student_post_interaction(
            db,
            company_user_id=companies["aero_ai"].id,
            student_post_id=students["petros"][2].id,
            saved=False,
            decision=Decision.LIKE,
            saved_at=None,
            decided_at=datetime.utcnow(),
        )

        db.commit()
        print("Seed completed successfully.")
        print("Demo logins:")
        print("Company: acme_hr / pass1234")
        print("Company: green_energy / pass1234")
        print("Company: medix_talent / pass1234")
        print("Company: finwave_jobs / pass1234")
        print("Company: logi_chain / pass1234")
        print("Company: aero_ai / pass1234")
        print("Company: campus_cafe / pass1234")
        print("Company: blue_marine / pass1234")
        print("Company: agrobyte / pass1234")
        print("Company: civic_soft / pass1234")
        print("Student: eleni / pass1234")
        print("Student: nikos / pass1234")
        print("Student: maria / pass1234")
        print("Student: giorgos / pass1234")
        print("Student: sofia / pass1234")
        print("Student: kostas / pass1234")
        print("Student: anna / pass1234")
        print("Student: dimitris / pass1234")
        print("Student: irene / pass1234")
        print("Student: petros / pass1234")

    finally:
        db.close()


if __name__ == "__main__":
    main()
