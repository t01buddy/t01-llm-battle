"""
LLM-as-judge scorer.
After a run completes, score each fighter_result using the battle's judge_provider/judge_model.
"""
import re
from .providers.registry import get_provider
from .providers.base import CompletionRequest

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
