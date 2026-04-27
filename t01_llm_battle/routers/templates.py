"""API router: board template discovery and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..template_service import list_templates, get_template_html

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def list_board_templates():
    """List all available board templates (bundled + user-custom)."""
    return list_templates()


@router.get("/{template_id}", response_class=HTMLResponse)
async def get_board_template(template_id: str):
    """Return the HTML content of a specific board template."""
    html = get_template_html(template_id)
    if html is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return HTMLResponse(content=html)
