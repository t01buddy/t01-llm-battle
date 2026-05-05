"""Sources router — upload/list/delete battle source items."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from ..db import get_db

router = APIRouter(prefix="/battles/{battle_id}/sources", tags=["sources"])


async def _battle_exists(battle_id: str) -> None:
    async with get_db() as db:
        row = await db.execute("SELECT id FROM battle WHERE id = ?", (battle_id,))
        if not await row.fetchone():
            raise HTTPException(status_code=404, detail="Battle not found")


async def _next_position(db, battle_id: str) -> int:
    cursor = await db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM battle_source WHERE battle_id = ?",
        (battle_id,),
    )
    row = await cursor.fetchone()
    return row[0]


@router.post("")
async def upload_source(
    battle_id: str,
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    label: str | None = Form(default=None),
):
    """Upload a source file (text, .md, or CSV) or raw text body.

    - Text / markdown files: one source item per file.
    - CSV files: one source item per data row (first column = content).
    - Raw text: provide `text` form field; `label` is optional.
    """
    await _battle_exists(battle_id)

    MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

    created: list[dict] = []

    async with get_db() as db:
        if file is not None:
            filename = file.filename or "upload"
            raw = await file.read()
            if len(raw) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum upload size is 10 MB.",
                )

            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
            if ext not in ("txt", "md", "csv"):
                raise HTTPException(
                    status_code=422,
                    detail="Unsupported file type. Only .txt, .md, and .csv files are accepted.",
                )

            if ext == "csv":
                # Each row becomes a separate source item
                try:
                    text_content = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=422,
                        detail="File is not valid UTF-8 text.",
                    )
                reader = csv.reader(io.StringIO(text_content))
                rows = list(reader)

                # Skip header row if present (heuristic: first cell is non-numeric)
                data_rows = rows
                if rows and not rows[0][0].lstrip("-").replace(".", "", 1).isdigit():
                    data_rows = rows[1:]

                position = await _next_position(db, battle_id)
                for i, row in enumerate(data_rows):
                    if not row:
                        continue
                    row_label = f"Row {i + 1}"
                    content = row[0]
                    source_id = str(uuid.uuid4())
                    await db.execute(
                        "INSERT INTO battle_source (id, battle_id, label, content, position) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (source_id, battle_id, row_label, content, position + i),
                    )
                    created.append({"id": source_id, "label": row_label})
            else:
                # Text / markdown — one item per file
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=422,
                        detail="File is not valid UTF-8 text.",
                    )
                source_id = str(uuid.uuid4())
                position = await _next_position(db, battle_id)
                await db.execute(
                    "INSERT INTO battle_source (id, battle_id, label, content, position) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_id, battle_id, filename, content, position),
                )
                created.append({"id": source_id, "label": filename})

        elif text is not None:
            item_label = label or f"Source {datetime.now(timezone.utc).isoformat()}"
            source_id = str(uuid.uuid4())
            async with get_db() as db2:
                position = await _next_position(db2, battle_id)
                await db2.execute(
                    "INSERT INTO battle_source (id, battle_id, label, content, position) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_id, battle_id, item_label, text, position),
                )
                await db2.commit()
            return JSONResponse(status_code=201, content={"id": source_id, "label": item_label})

        else:
            raise HTTPException(
                status_code=422,
                detail="Provide either a file upload or a `text` form field.",
            )

        await db.commit()

    if not created:
        raise HTTPException(status_code=422, detail="No source items were extracted from the upload.")

    return JSONResponse(status_code=201, content={"sources": created})


@router.get("")
async def list_sources(battle_id: str):
    """List all source items for a battle, ordered by position."""
    await _battle_exists(battle_id)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, label, position FROM battle_source "
            "WHERE battle_id = ? ORDER BY position",
            (battle_id,),
        )
        rows = await cursor.fetchall()

    return {"sources": [{"id": r["id"], "label": r["label"], "position": r["position"]} for r in rows]}


@router.delete("/{source_id}", status_code=204, response_model=None)
async def delete_source(battle_id: str, source_id: str):
    """Delete a single source item."""
    await _battle_exists(battle_id)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM battle_source WHERE id = ? AND battle_id = ?",
            (source_id, battle_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Source not found")

        await db.execute(
            "DELETE FROM battle_source WHERE id = ? AND battle_id = ?",
            (source_id, battle_id),
        )
        await db.commit()
