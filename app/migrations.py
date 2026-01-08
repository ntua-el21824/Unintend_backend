from __future__ import annotations

from sqlalchemy import text


# Simple SQLite-only "add missing columns" helper.
# This project does not use Alembic migrations.


def ensure_sqlite_columns(engine) -> None:
    url = str(engine.url)
    if not url.startswith("sqlite"):
        return

    # table -> (column -> ddl)
    needed: dict[str, dict[str, str]] = {
        "users": {
            "profile_image_url": "TEXT",
        },
        "internship_posts": {
            "image_url": "TEXT",
        },
        "student_profile_posts": {
            "image_url": "TEXT",
        },
        "student_experience_posts": {
            "image_url": "TEXT",
        },
    }

    with engine.connect() as conn:
        for table_name, columns in needed.items():
            rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            existing = {row[1] for row in rows}  # row[1] = column name

            for column_name, ddl in columns.items():
                if column_name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))

        conn.commit()
