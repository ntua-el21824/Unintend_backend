from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .db import engine, Base
from .routers.auth_routes import router as auth_router
from .routers.posts_routes import router as posts_router
from .routers.feed_routes import router as feed_router
from .routers.interaction_routes import router as interactions_router
from .routers.application_routes import router as applications_router
from .routers.chat_routes import router as chat_router
from .routers.profile_posts_routes import router as profile_posts_router
from .routers.media_routes import router as media_router
from app.routers import saves_routes
from .migrations import ensure_sqlite_columns

app = FastAPI(title="UnIntend Backend")

# CORS (για Flutter debug, emulator κλπ)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # για μάθημα OK
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables (simple approach)
Base.metadata.create_all(bind=engine)

# Ensure new columns exist for SQLite (no Alembic migrations in this project)
ensure_sqlite_columns(engine)

# Serve uploaded images
uploads_dir = (Path(__file__).resolve().parent.parent / "uploads")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

app.include_router(auth_router)
app.include_router(posts_router)
app.include_router(feed_router)
app.include_router(interactions_router)
app.include_router(applications_router)
app.include_router(chat_router)
app.include_router(profile_posts_router)
app.include_router(media_router)
app.include_router(saves_routes.router)


@app.get("/")
def root():
    return {"ok": True, "service": "UnIntend Backend"}
