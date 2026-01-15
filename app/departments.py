from __future__ import annotations

import re
from dataclasses import dataclass


CANONICAL_DEPARTMENTS: tuple[str, ...] = (
    "Human Resources (HR)",
    "Marketing",
    "Public Relations (PR)",
    "Sales",
    "Legal Department",
    "IT",
    "Supply Chain",
    "Data Analytics",
    "Product Management",
    "Software Development",
)

_CANONICAL_LOWER = {d.lower(): d for d in CANONICAL_DEPARTMENTS}

# Acceptable query inputs / legacy values -> canonical
_DEPARTMENT_SYNONYMS: dict[str, str] = {
    "hr": "Human Resources (HR)",
    "human resources": "Human Resources (HR)",
    "human resources (hr)": "Human Resources (HR)",

    "marketing": "Marketing",

    "pr": "Public Relations (PR)",
    "public relations": "Public Relations (PR)",
    "public relations (pr)": "Public Relations (PR)",

    "sales": "Sales",

    "legal": "Legal Department",
    "legal department": "Legal Department",

    "it": "IT",

    "supply chain": "Supply Chain",

    "data": "Data Analytics",
    "data analytics": "Data Analytics",

    "product": "Product Management",
    "product management": "Product Management",

    "software development": "Software Development",
    "software": "Software Development",
}


def normalize_department(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    # Treat UI's All as "no filter"
    if cleaned.lower() == "all":
        return None

    # Exact canonical (case-insensitive)
    canonical = _CANONICAL_LOWER.get(cleaned.lower())
    if canonical:
        return canonical

    # Known synonyms
    synonym = _DEPARTMENT_SYNONYMS.get(cleaned.lower())
    if synonym:
        return synonym

    return cleaned


def is_canonical_department(value: str | None) -> bool:
    if value is None:
        return False
    return value in CANONICAL_DEPARTMENTS


@dataclass(frozen=True)
class Guess:
    department: str
    confidence: int  # 1=low, 2=medium, 3=high


def _contains(text: str, *needles: str) -> bool:
    return any(n in text for n in needles)


def guess_department(title: str | None, description: str | None) -> Guess | None:
    """Guess canonical department from free text.

    Returns Guess with confidence. Intended for one-off DB normalization only.
    """
    hay = f"{title or ''} {description or ''}".lower()
    hay = re.sub(r"\s+", " ", hay).strip()
    if not hay:
        return None

    # Legal
    if _contains(hay, "gdpr", "compliance", "legal", "law"):
        return Guess("Legal Department", 3)

    # HR
    if _contains(hay, "human resources", "people operations", "recruit", "talent", "hr ", " hr"):
        return Guess("Human Resources (HR)", 3)

    # Marketing
    if _contains(hay, "social media"):
        return Guess("Marketing", 3)
    if _contains(hay, "marketing"):
        return Guess("Marketing", 3)
    if _contains(hay, "brand communication"):
        return Guess("Marketing", 3)
    if _contains(hay, "marketing", "brand", "campaign"):
        return Guess("Marketing", 2)

    # PR (avoid matching generic "media" which often appears in marketing)
    if _contains(hay, "public relations", " pr ", "communications", "press"):
        return Guess("Public Relations (PR)", 3)
    if _contains(hay, "media", "events") and _contains(hay, "pr"):
        return Guess("Public Relations (PR)", 3)

    # Product Management
    if _contains(hay, "product management", "product manager", "product analyst"):
        return Guess("Product Management", 3)
    if _contains(hay, "product ") or hay.startswith("product"):
        return Guess("Product Management", 2)

    # Sales
    if _contains(hay, "business development", "sales", "crm", "leads", "pipeline", "bd "):
        return Guess("Sales", 3)

    # Supply Chain
    if _contains(hay, "supply chain", "logistics", "procurement", "warehouse"):
        return Guess("Supply Chain", 3)

    # IT
    if _contains(hay, "information technology", "helpdesk", "sysadmin", "network", "it ", " it"):
        return Guess("IT", 3)

    # Software Development
    if _contains(hay, "backend", "frontend", "fullstack", "flutter", "react", "typescript", "fastapi", "qa", "automation", "devops"):
        return Guess("Software Development", 3)
    if _contains(hay, "software", "engineering", "developer", "mobile"):
        return Guess("Software Development", 2)

    # Data Analytics
    if _contains(hay, "business intelligence", "etl", "computer vision", "machine learning"):
        return Guess("Data Analytics", 3)
    if _contains(hay, "data", "analytics", "bi"):
        return Guess("Data Analytics", 2)

    return None
