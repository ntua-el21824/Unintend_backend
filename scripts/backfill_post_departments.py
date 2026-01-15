"""Normalize InternshipPost.department values to match the frontend dropdown.

Why this exists:
- SQLite DB has no constraints, so department values can be NULL, empty, or inconsistent.
- The frontend expects a fixed set of labels.

What this does:
- Normalizes case/whitespace.
- Maps known synonyms to canonical labels.
- Optionally reclassifies rows if the text strongly indicates a different canonical department.

Usage:
    C:/Users/eleni/unintend_backend/.venv/Scripts/python.exe scripts/backfill_post_departments.py
    C:/Users/eleni/unintend_backend/.venv/Scripts/python.exe scripts/backfill_post_departments.py --dry-run
    C:/Users/eleni/unintend_backend/.venv/Scripts/python.exe scripts/backfill_post_departments.py --no-reclassify
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.departments import CANONICAL_DEPARTMENTS, guess_department, normalize_department


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="unintend.db", help="Path to sqlite DB (default: unintend.db)")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--no-reclassify", action="store_true", help="Do not change existing canonical departments")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path.resolve()}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, title, description, department FROM internship_posts")
    rows = cur.fetchall()

    updates: list[tuple[str, int]] = []
    changed_missing = 0
    changed_normalized = 0
    changed_reclassified = 0

    canonical_set = set(CANONICAL_DEPARTMENTS)

    for post_id, title, description, current in rows:
        current_norm = normalize_department(current)
        guessed = guess_department(title, description)

        # 1) Fill missing/empty
        if current_norm is None:
            if guessed:
                updates.append((guessed.department, post_id))
                changed_missing += 1
            continue

        # 2) Normalize to exact canonical spelling if possible
        if current_norm in canonical_set and current != current_norm:
            updates.append((current_norm, post_id))
            changed_normalized += 1
            continue

        # 3) If non-canonical, try to map/guess to canonical
        if current_norm not in canonical_set:
            if guessed:
                updates.append((guessed.department, post_id))
                changed_normalized += 1
            continue

        # 4) Reclassify only when the guess is high-confidence and differs
        if not args.no_reclassify and guessed and guessed.confidence >= 3 and guessed.department != current_norm:
            updates.append((guessed.department, post_id))
            changed_reclassified += 1

    print(f"total posts: {len(rows)}")
    print(f"planned updates: {len(updates)}")
    print(f"- fill missing: {changed_missing}")
    print(f"- normalize/map: {changed_normalized}")
    print(f"- reclassify: {changed_reclassified}")

    if args.dry_run:
        for dept, post_id in updates[:50]:
            print(f"id={post_id} -> {dept}")
        if len(updates) > 50:
            print(f"... ({len(updates) - 50} more)")
        return 0

    if updates:
        cur.executemany("UPDATE internship_posts SET department = ? WHERE id = ?", updates)
        conn.commit()

    # Summary
    cur.execute("SELECT department, COUNT(*) c FROM internship_posts GROUP BY department ORDER BY c DESC")
    print("departments after backfill:")
    for dept, c in cur.fetchall():
        print(repr(dept), c)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
