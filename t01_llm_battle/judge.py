"""
LLM-as-judge scorer.
After a run completes, score each fighter_result using the battle's judge_provider/judge_model.
"""
import re
from .providers.registry import get_provider
from .providers.base import CompletionRequest
from .db import get_db

DEFAULT_JUDGE_PROMPT = """You are evaluating an AI assistant's response to a task.

Task/Source:
{source}

Response:
{response}

Evaluation criteria:
{rubric}

Score the response from 0-10 and explain your reasoning.
Your response MUST end with a line in this exact format:
SCORE: <number>
"""


async def score_response(
    judge_provider: str,
    judge_model: str,
    judge_rubric: str,
    source_content: str,
    response_content: str,
) -> tuple[float | None, str]:
    """
    Returns (score, explanation).
    score is 0-10 float or None if parsing failed.
    """
    try:
        provider = get_provider(judge_provider)
        prompt = DEFAULT_JUDGE_PROMPT.format(
            source=source_content,
            response=response_content,
            rubric=judge_rubric or "Quality, accuracy, and helpfulness.",
        )
        result = await provider.complete(
            CompletionRequest(
                model=judge_model,
                system_prompt="You are an objective evaluator. Always end with 'SCORE: <0-10>'.",
                user_prompt=prompt,
            )
        )
        # Parse score from last line
        score = None
        for line in reversed(result.content.splitlines()):
            m = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", line, re.IGNORECASE)
            if m:
                score = min(10.0, max(0.0, float(m.group(1))))
                break
        return score, result.content
    except Exception as e:
        return None, f"Judge error: {e}"


async def generate_report(
    run_id: str,
    judge_provider: str,
    judge_model: str,
    db_path: str,
) -> str:
    """Generate a markdown summary report for the run using the judge model.

    Returns the markdown string (or an error message if generation fails).
    The result is stored in run.report_markdown.
    """
    try:
        # 1. Load all fighter_results with scores
        async with get_db(db_path) as db:
            cursor = await db.execute(
                """
                SELECT fr.fighter_id, fr.source_id, fr.final_output,
                       fr.total_cost_usd, fr.total_latency_ms,
                       fr.judge_score, fr.judge_reasoning,
                       f.name AS fighter_name,
                       bs.label AS source_label
                FROM fighter_result fr
                JOIN fighter f ON f.id = fr.fighter_id
                JOIN battle_source bs ON bs.id = fr.source_id
                WHERE fr.run_id = ? AND fr.judge_score IS NOT NULL
                ORDER BY f.position, bs.position
                """,
                (run_id,),
            )
            rows = [dict(r) for r in await cursor.fetchall()]

        if not rows:
            return "Report generation failed: no judged results found."

        # 2. Build per-fighter summary data
        fighter_data: dict[str, dict] = {}
        for r in rows:
            fid = r["fighter_id"]
            if fid not in fighter_data:
                fighter_data[fid] = {
                    "name": r["fighter_name"],
                    "scores": [],
                    "total_cost_usd": 0.0,
                    "total_latency_ms": 0,
                    "results": [],
                }
            fd = fighter_data[fid]
            fd["scores"].append(r["judge_score"])
            fd["total_cost_usd"] += r["total_cost_usd"] or 0.0
            fd["total_latency_ms"] += r["total_latency_ms"] or 0
            # Trim reasoning to a short snippet
            reasoning_snippet = ""
            if r["judge_reasoning"]:
                snippet = r["judge_reasoning"].strip()
                reasoning_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
            fd["results"].append({
                "source_label": r["source_label"],
                "score": r["judge_score"],
                "reasoning_snippet": reasoning_snippet,
            })

        # 3. Build prompt summarising all results
        summary_lines = []
        for fid, fd in fighter_data.items():
            avg_score = sum(fd["scores"]) / len(fd["scores"]) if fd["scores"] else 0.0
            summary_lines.append(
                f"Fighter: {fd['name']}\n"
                f"  Average Score: {avg_score:.2f}/10\n"
                f"  Total Cost: ${fd['total_cost_usd']:.4f}\n"
                f"  Total Latency: {fd['total_latency_ms']}ms\n"
                f"  Individual Results:"
            )
            for res in fd["results"]:
                summary_lines.append(
                    f"    - Source '{res['source_label']}': "
                    f"Score {res['score']}/10 — {res['reasoning_snippet']}"
                )

        summary_text = "\n".join(summary_lines)

        report_prompt = (
            "You are writing a battle report comparing AI language models.\n\n"
            "Here are the evaluation results:\n\n"
            f"{summary_text}\n\n"
            "Please write a comprehensive markdown report with the following sections:\n"
            "1. ## Rankings — rank fighters from best to worst by average score\n"
            "2. ## Per-Fighter Summary — for each fighter, summarise their strengths and weaknesses\n"
            "3. ## Cost & Latency Comparison — compare total cost and latency across fighters\n"
            "4. ## Notable Observations — any interesting patterns, surprises, or insights\n\n"
            "Use proper markdown formatting with headers, tables where appropriate, and bullet points."
        )

        # 4. Call provider.complete
        provider = get_provider(judge_provider)
        result = await provider.complete(
            CompletionRequest(
                model=judge_model,
                system_prompt="You are an expert technical writer producing clear, insightful battle reports.",
                user_prompt=report_prompt,
            )
        )
        markdown = result.content

        # 5. Store in run.report_markdown
        async with get_db(db_path) as db:
            await db.execute(
                "UPDATE run SET report_markdown = ? WHERE id = ?",
                (markdown, run_id),
            )
            await db.commit()

        # 6. Return markdown
        return markdown

    except Exception as e:
        return f"Report generation failed: {e}"
