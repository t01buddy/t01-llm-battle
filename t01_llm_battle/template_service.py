"""Board template discovery: bundled + user-custom templates."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

_BUNDLED_DIR = Path(__file__).parent / "board_templates"
_USER_DIR = Path.home() / ".t01-llm-battle" / "templates"

_BUNDLED_META: dict[str, str] = {
    "card-grid": "Card Grid",
    "news-feed": "News Feed List",
}


class TemplateInfo(TypedDict):
    id: str
    name: str
    source: str  # "bundled" | "user"
    path: str


def list_templates() -> list[TemplateInfo]:
    """Return all available templates (bundled first, then user-custom)."""
    results: list[TemplateInfo] = []

    for stem, label in _BUNDLED_META.items():
        html_path = _BUNDLED_DIR / f"{stem}.html"
        if html_path.exists():
            results.append({"id": stem, "name": label, "source": "bundled", "path": str(html_path)})

    if _USER_DIR.exists():
        for html_file in sorted(_USER_DIR.glob("*.html")):
            tid = html_file.stem
            if any(t["id"] == tid for t in results):
                continue  # user cannot override bundled names
            results.append({"id": tid, "name": tid.replace("-", " ").title(), "source": "user", "path": str(html_file)})

    return results


def get_template_path(template_id: str) -> Path | None:
    """Return resolved Path for a template ID, or None if not found."""
    for t in list_templates():
        if t["id"] == template_id:
            return Path(t["path"])
    return None


def get_template_html(template_id: str) -> str | None:
    """Return HTML content for a template ID, or None if not found."""
    path = get_template_path(template_id)
    return path.read_text(encoding="utf-8") if path else None
