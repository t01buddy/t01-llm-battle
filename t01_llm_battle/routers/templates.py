"""API router: board template discovery, retrieval, upload, and deletion."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, UploadFile

from fastapi.responses import HTMLResponse

from ..template_service import (
    list_templates,
    get_template_html,
    save_user_template,
    delete_user_template,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])

_VALID_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')


@router.get("")
async def list_board_templates():
    """List all available board templates (bundled + user-custom)."""
    return list_templates()


@router.post("", status_code=201)
async def upload_user_template(file: UploadFile):
    """Upload a user-custom HTML template.

    The template ID is derived from the filename (stem, lowercased).
    Accepts only .html files. Cannot overwrite bundled templates.
    """
    filename = file.filename or ""
    if not filename.lower().endswith(".html"):
        raise HTTPException(status_code=422, detail="Only .html files are accepted")

    template_id = filename[:-5].lower()  # strip .html
    if not _VALID_ID.match(template_id):
        raise HTTPException(
            status_code=422,
            detail="Template ID (filename stem) must be lowercase alphanumeric with hyphens, 1–64 chars",
        )

    content = await file.read()
    info = save_user_template(template_id, content)
    return info


@router.get("/{template_id}", response_class=HTMLResponse)
async def get_board_template(template_id: str):
    """Return the HTML content of a specific board template."""
    html = get_template_html(template_id)
    if html is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return HTMLResponse(content=html)


@router.delete("/{template_id}", status_code=204)
async def delete_board_template(template_id: str):
    """Delete a user-custom template. Bundled templates cannot be deleted."""
    try:
        found = delete_user_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not found:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
