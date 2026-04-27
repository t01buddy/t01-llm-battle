"""Board publishing — static export and GitHub Pages push (FR-29)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from .template_service import get_template_html

log = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = "card-grid"


def _build_data_json(board: dict, items: list[dict]) -> str:
    """Return serialised data.json payload."""
    return json.dumps(
        {
            "board": {
                "id": board.get("id", ""),
                "name": board.get("name", ""),
                "description": board.get("description", ""),
            },
            "items": [
                {
                    "title": it.get("title", ""),
                    "url": it.get("source_url", ""),
                    "summary": it.get("summary", ""),
                    "tags": it.get("tags", []),
                    "category": it.get("category", ""),
                    "score": it.get("relevance_score"),
                    "published_at": it.get("published_at"),
                }
                for it in items
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _get_html(template_id: str | None) -> str:
    tid = template_id or _DEFAULT_TEMPLATE
    html = get_template_html(tid)
    if html is None:
        html = get_template_html(_DEFAULT_TEMPLATE) or ""
    return html


# ---------------------------------------------------------------------------
# Static export
# ---------------------------------------------------------------------------


def publish_static(
    board: dict,
    items: list[dict],
    output_dir: str,
    template_id: str | None = None,
) -> None:
    """Write index.html + data.json to *output_dir*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(_build_data_json(board, items), encoding="utf-8")
    (out / "index.html").write_text(_get_html(template_id), encoding="utf-8")
    log.info("[publisher] static export → %s", out)


# ---------------------------------------------------------------------------
# GitHub Pages push
# ---------------------------------------------------------------------------


async def publish_github_pages(
    board: dict,
    items: list[dict],
    gh_token: str,
    repo: str,
    branch: str = "gh-pages",
    template_id: str | None = None,
) -> None:
    """Push index.html + data.json to the gh-pages branch via GitHub API."""
    html_content = _get_html(template_id)
    data_content = _build_data_json(board, items)

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for filename, content in [("index.html", html_content), ("data.json", data_content)]:
            encoded = base64.b64encode(content.encode()).decode()
            url = f"https://api.github.com/repos/{repo}/contents/{filename}"

            # Check if file exists to get its SHA (required for updates)
            sha: str | None = None
            try:
                r = await client.get(url, params={"ref": branch})
                if r.status_code == 200:
                    sha = r.json().get("sha")
            except Exception:
                pass

            payload: dict[str, Any] = {
                "message": f"publish: update {filename}",
                "content": encoded,
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            r = await client.put(url, json=payload)
            if r.status_code not in (200, 201):
                raise RuntimeError(
                    f"GitHub API error {r.status_code} for {filename}: {r.text[:200]}"
                )

    log.info("[publisher] GitHub Pages → %s@%s", repo, branch)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def publish_board(
    board: dict,
    items: list[dict],
    publish_config: dict,
) -> dict[str, Any]:
    """
    Dispatch publish based on publish_config.

    Config keys:
      target: "static" | "github_pages" | None
      output_dir: str  (static)
      gh_token: str    (github_pages)
      repo: str        (github_pages, e.g. "owner/repo")
      branch: str      (github_pages, default "gh-pages")
      template_id: str (optional)
    """
    target = publish_config.get("target")
    template_id = publish_config.get("template_id") or board.get("template_id")

    if target == "static":
        output_dir = publish_config.get("output_dir", "")
        if not output_dir:
            return {"ok": False, "error": "output_dir is required for static target"}
        await asyncio.to_thread(publish_static, board, items, output_dir, template_id)
        return {"ok": True, "target": "static", "output_dir": output_dir}

    if target == "github_pages":
        gh_token = publish_config.get("gh_token", "")
        repo = publish_config.get("repo", "")
        branch = publish_config.get("branch", "gh-pages")
        if not gh_token or not repo:
            return {"ok": False, "error": "gh_token and repo are required for github_pages target"}
        await publish_github_pages(board, items, gh_token, repo, branch, template_id)
        return {"ok": True, "target": "github_pages", "repo": repo, "branch": branch}

    return {"ok": False, "error": f"unknown or missing publish target: {target!r}"}
