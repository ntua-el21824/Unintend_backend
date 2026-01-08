from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///./unintend.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite requirement
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
