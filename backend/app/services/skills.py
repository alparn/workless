"""Shared skill-loading utilities used across graph nodes."""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skill(filename: str) -> str:
    return (SKILLS_DIR / filename).read_text(encoding="utf-8")
