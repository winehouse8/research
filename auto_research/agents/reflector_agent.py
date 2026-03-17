"""Reflector agent: extracts actionable annotations from comparison reasoning.

Uses Claude Agent SDK with no tools (pure reasoning).
Uses claude-haiku-4-5 for cost-efficient annotation extraction.

Prompt design principles:
- Research question is the lens through which ALL insights are evaluated
- Three structured categories: knowledge gaps, boundary conditions, methodology
- Every annotation must be ACTIONABLE (could the next agent act on it?)
- suggested_search field directly feeds the next research cycle
- Receives judge REASONING (not just win/loss) for evidence-based reflection
"""

import json
import logging
from typing import List, Dict

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

from auto_research.agents._sdk import enforce_reflection_quality

logger = logging.getLogger("autoresearch.reflector")

REFLECTION_PROMPT = """You are a research reflector in an evolutionary knowledge ecosystem.
Your job is to extract ACTIONABLE insights that will guide the NEXT research cycle.

## Research Question (the north star)
{research_question}

## New Paper
Claim: {new_claim}
Summary: {new_summary}
Assumptions: {new_assumptions}

## Comparison Result
{comparison_result}

## Current Knowledge State
{context}

## Your Task
Analyze this cycle's outcome and extract insights in THREE categories:

1. KNOWLEDGE GAPS: What aspects of the research question remain unanswered
   or poorly evidenced? What should the NEXT paper investigate?
   (Tag: evidence_gap, question, direction)

2. BOUNDARY CONDITIONS: What limitations, conditions, or contradictions
   were revealed? Under what circumstances does the claim fail or weaken?
   (Tag: limitation, condition, contradiction, scope_boundary)

3. METHODOLOGY: What worked or failed in the evidence-gathering approach?
   What search strategies or source types should future papers prioritize?
   (Tag: methodology, confirmation)

For each insight, ask: "Could the next research agent act on this?"
If not, the insight is too vague.

BAD example: "More evidence is needed on this topic."
GOOD example: "The claim about memory consolidation lacks evidence for
distributed systems with >100 nodes. Next paper should search for
benchmarks comparing centralized vs. distributed memory architectures."

Output a JSON array of 2-4 annotations:
[
  {{"content": "Specific, actionable insight", "tags": ["tag1", "tag2"],
    "suggested_search": "A specific search query the next researcher could use"}}
]

Output ONLY the JSON array, nothing else."""


async def run_reflection(
    conn,
    session_id: str,
    topic: str,
    comparison_result,
    new_paper: dict,
    context: str = "",
    research_question: str = "",
) -> List[Dict]:
    """Extract annotations from comparison reasoning using Claude Agent SDK.

    Args:
        conn: SQLite connection (unused here, kept for interface consistency).
        session_id: Current session ID.
        topic: Research topic.
        comparison_result: Tuple of (winner_id, loser_id, reasoning) or None.
        new_paper: The newly generated paper dict.
        context: Current session context string.
        research_question: The overarching research question.

    Returns:
        List of annotation dicts with 'content' and 'tags' keys.
    """
    comp_text = "No comparison was made (claims were orthogonal or position bias detected)."
    if comparison_result:
        winner_id = comparison_result[0]
        loser_id = comparison_result[1]
        reasoning = comparison_result[2] if len(comparison_result) > 2 else ""

        if winner_id == new_paper.get("id"):
            comp_text = f"The new paper WON against rival {loser_id}."
        else:
            comp_text = f"The new paper LOST against rival {winner_id}."

        if reasoning:
            comp_text += f"\nJudge's reasoning: {reasoning}"

    prompt = REFLECTION_PROMPT.format(
        new_claim=new_paper.get("claim", ""),
        new_summary=new_paper.get("l1_summary", "")[:500],
        new_assumptions=new_paper.get("assumptions", "None stated"),
        comparison_result=comp_text,
        context=context[:1000] if context else "No prior context.",
        research_question=research_question or "N/A",
    )

    logger.info("Extracting annotations from comparison")
    logger.debug(f"=== REFLECTOR PROMPT ===\n{prompt}")

    try:
        result_text = ""
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=[],
                permission_mode="bypassPermissions",
                model="claude-haiku-4-5-20251001",
                max_turns=3,
                hooks={
                    "Stop": [HookMatcher(matcher="*", hooks=[enforce_reflection_quality])]
                },
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""

        result_text = result_text.strip()
        logger.debug(f"=== REFLECTOR RESULT ===\n{result_text}")

        annotations = _parse_annotations(result_text)
        logger.info(f"Extracted {len(annotations)} annotations")
        return annotations

    except Exception as e:
        logger.error(f"Reflector error: {e}")
        return [{
            "content": f"Reflection failed: {str(e)[:200]}",
            "tags": ["error"],
        }]


def _parse_annotations(text: str) -> List[Dict]:
    """Parse LLM output into annotation list with validation."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        annotations = json.loads(text)

        if not isinstance(annotations, list):
            annotations = [annotations]

        valid = []
        valid_tags = {
            "limitation", "contradiction", "confirmation", "methodology",
            "question", "direction", "condition", "evidence_gap",
            "scope_boundary", "superseded", "convergence", "prediction",
            "relevance_gap", "error",
        }

        for ann in annotations:
            if isinstance(ann, dict) and "content" in ann:
                tags = ann.get("tags", [])
                if isinstance(tags, list):
                    tags = [t for t in tags if t in valid_tags] or ["general"]
                else:
                    tags = ["general"]
                valid.append({
                    "content": str(ann["content"]),
                    "tags": tags,
                    "suggested_search": ann.get("suggested_search", ""),
                })

        return valid if valid else [{"content": "No clear insights extracted", "tags": ["general"]}]

    except (json.JSONDecodeError, IndexError):
        return [{"content": text[:300] if text else "Parse failed", "tags": ["error"]}]
