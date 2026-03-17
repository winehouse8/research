"""Compare agent: pairwise LLM-as-Judge with position bias removal.

Uses Claude Agent SDK with no tools (pure reasoning).
Uses claude-haiku-4-5 for cost-efficient repeated comparisons.

Prompt design principles:
- Research question is the PRIMARY evaluation criterion (relevance > general quality)
- Claim classification is RELATIVE to the research question, not absolute
- Lakatos: operationalized with specific criteria, not abstract mention
- Popper: papers with unfalsifiable assumptions are penalized
- Chain-of-thought in classification for better accuracy
"""

import json
import logging
import sqlite3
from typing import Optional, Tuple
from datetime import datetime, timezone

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

from auto_research.agents._sdk import enforce_comparison_quality

logger = logging.getLogger("autoresearch.compare")

CLASSIFY_PROMPT = """You are classifying claims in the context of this research question:
{research_question}

Claim A: {claim_a}
Claim B: {claim_b}

Classify their relationship WITH RESPECT TO THE RESEARCH QUESTION:
- "opposing": They give CONFLICTING answers or recommendations. This includes:
  direct contradiction, incompatible scope claims (A says "always works" vs B says
  "only works under X"), or incompatible mechanisms (A says cause is X, B says cause is Y).
- "complementary": They give COMPATIBLE answers that together provide a more complete
  picture. Different evidence for the same conclusion, or answers to different
  sub-questions that do not conflict.
- "orthogonal": They address UNRELATED aspects with no meaningful interaction,
  even considering the research question.

If you are uncertain, respond "orthogonal".

Think step-by-step:
1. What sub-question of the research question does Claim A address?
2. What sub-question does Claim B address?
3. Do their answers conflict, complement, or ignore each other?

Output your reasoning in one sentence, then on a NEW LINE output ONLY the
classification word (opposing, complementary, or orthogonal)."""

JUDGE_OPPOSING_PROMPT = """You are a scientific judge evaluating two competing claims.

## Research Question (this defines what "better" means)
{research_question}

## Paper A
Claim: {claim_a}
Evidence: {evidence_a}
Assumptions (boundary conditions): {assumptions_a}

## Paper B
Claim: {claim_b}
Evidence: {evidence_b}
Assumptions (boundary conditions): {assumptions_b}

## Evaluation Criteria (in priority order)
1. RELEVANCE: Which claim more directly answers the research question?
   A brilliant paper about the wrong question loses to a decent paper about the right one.
2. EVIDENCE QUALITY: Which claim is better supported by its cited evidence?
   Peer-reviewed sources > technical reports > blog posts.
   Multiple independent sources > single source.
3. FALSIFIABILITY: Which paper has more specific, testable assumptions?
   "Works under conditions X, Y, Z" > "Generally applicable."
   PENALTY: If a paper's assumptions are vague (e.g., "standard conditions",
   "None stated"), treat it as WEAKER because unfalsifiable claims cannot
   be scientifically evaluated.
4. LAKATOS PROGRESSIVENESS: Which claim makes NEW testable predictions
   beyond its evidence? A claim that only explains known facts is weaker
   than one that predicts something new and verifiable.

Respond with ONLY a JSON object:
{{"winner": "A" or "B", "reasoning": "1-2 sentences citing which criteria decided it"}}
No other text."""


async def run_comparison(
    conn: sqlite3.Connection,
    paper_a: dict,
    paper_b: dict,
    research_question: str = "",
) -> Optional[Tuple[str, str, str]]:
    """Run pairwise comparison with position bias removal.

    Args:
        conn: SQLite connection.
        paper_a: First paper dict.
        paper_b: Second paper dict.
        research_question: The overarching research question.

    Returns:
        Tuple of (winner_id, loser_id, reasoning) if unanimous,
        None if disagreement or orthogonal.
    """
    if not paper_a or not paper_b:
        logger.warning("Cannot compare: missing paper(s)")
        return None

    if paper_a.get("id") == paper_b.get("id"):
        logger.warning("Cannot compare paper with itself")
        return None

    # Step 1: Classify claims
    relation = await _classify_claims(paper_a["claim"], paper_b["claim"], research_question)
    logger.info(f"Claim relation: {relation}")

    if relation == "orthogonal":
        logger.info("Orthogonal claims — skipping comparison")
        return None

    # Complementary papers: both benefit (no winner/loser)
    # Strategy report: "보완 논문은 둘 다 fitness 상승"
    if relation == "complementary":
        logger.info("Complementary claims — both papers benefit (no competition)")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO comparisons (winner, loser, created_at) VALUES (?, ?, ?)",
            (paper_a["id"], paper_b["id"], now),
        )
        conn.execute(
            "INSERT INTO comparisons (winner, loser, created_at) VALUES (?, ?, ?)",
            (paper_b["id"], paper_a["id"], now),
        )
        conn.commit()
        logger.info(f"Mutual reinforcement recorded: {paper_a['id']} <-> {paper_b['id']}")
        return (paper_a["id"], paper_b["id"], "Complementary claims — mutual reinforcement")

    # Step 2: Position bias removal — judge A->B then B->A (opposing only)
    # Forward: A first, B second
    result_forward, reasoning_forward = await _judge(JUDGE_OPPOSING_PROMPT, paper_a, paper_b, research_question)
    # Reverse: B first, A second
    result_reverse, reasoning_reverse = await _judge(JUDGE_OPPOSING_PROMPT, paper_b, paper_a, research_question)

    if result_forward is None or result_reverse is None:
        logger.warning("Judge returned invalid result")
        return None

    # Map results back to paper IDs
    forward_winner_id = paper_a["id"] if result_forward == "A" else paper_b["id"]
    reverse_winner_id = paper_b["id"] if result_reverse == "A" else paper_a["id"]

    # Unanimous check
    if forward_winner_id != reverse_winner_id:
        logger.info("Position bias detected — no winner recorded")
        return None

    winner_id = forward_winner_id
    loser_id = paper_b["id"] if winner_id == paper_a["id"] else paper_a["id"]
    reasoning = reasoning_forward or ""

    # Record comparison
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO comparisons (winner, loser, created_at) VALUES (?, ?, ?)",
        (winner_id, loser_id, now),
    )
    conn.commit()

    logger.info(f"Comparison recorded: {winner_id} > {loser_id} | {reasoning[:80]}")
    return (winner_id, loser_id, reasoning)


async def _classify_claims(claim_a: str, claim_b: str, research_question: str = "") -> str:
    """Classify the relationship between two claims using Claude Agent SDK."""
    formatted_prompt = CLASSIFY_PROMPT.format(
        claim_a=claim_a, claim_b=claim_b, research_question=research_question or "N/A"
    )
    logger.debug(f"=== CLASSIFY PROMPT ===\n{formatted_prompt}")
    try:
        result_text = ""
        async for message in query(
            prompt=CLASSIFY_PROMPT.format(
                claim_a=claim_a,
                claim_b=claim_b,
                research_question=research_question or "N/A",
            ),
            options=ClaudeAgentOptions(
                allowed_tools=[],
                permission_mode="bypassPermissions",
                model="claude-haiku-4-5-20251001",
                max_turns=3,
                hooks={
                    "Stop": [HookMatcher(matcher="*", hooks=[enforce_comparison_quality])]
                },
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""

        logger.debug(f"=== CLASSIFY RESULT ===\n{result_text}")
        # Extract classification from last line (chain-of-thought response)
        lines = result_text.strip().split("\n")
        last_line = lines[-1].strip().lower() if lines else ""

        for word in ("opposing", "complementary", "orthogonal"):
            if word in last_line:
                return word
        # Fallback: search all lines
        full_text = result_text.lower()
        for word in ("opposing", "complementary", "orthogonal"):
            if word in full_text:
                return word
        return "orthogonal"

    except Exception as e:
        logger.error(f"Claim classification error: {e}")
        return "orthogonal"


async def _judge(
    prompt_template: str,
    paper_first: dict,
    paper_second: dict,
    research_question: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """Run a single judge call. Returns (winner 'A'/'B' or None, reasoning or None)."""
    evidence_a = paper_first.get("evidence_sources", "[]")
    if isinstance(evidence_a, list):
        evidence_a = json.dumps(evidence_a, ensure_ascii=False)
    evidence_b = paper_second.get("evidence_sources", "[]")
    if isinstance(evidence_b, list):
        evidence_b = json.dumps(evidence_b, ensure_ascii=False)

    prompt = prompt_template.format(
        claim_a=paper_first.get("claim", ""),
        claim_b=paper_second.get("claim", ""),
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        assumptions_a=paper_first.get("assumptions", "None"),
        assumptions_b=paper_second.get("assumptions", "None"),
        research_question=research_question or "N/A",
    )
    logger.debug(f"=== JUDGE PROMPT ===\n{prompt}")

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
                    "Stop": [HookMatcher(matcher="*", hooks=[enforce_comparison_quality])]
                },
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""

        result_text = result_text.strip()
        logger.debug(f"=== JUDGE RESULT ===\n{result_text}")

        if "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
            if result_text.startswith("json"):
                result_text = result_text[4:].strip()

        result = json.loads(result_text)
        winner = result.get("winner", "").upper()
        reasoning = result.get("reasoning", "")

        if winner in ("A", "B"):
            return winner, reasoning
        return None, None

    except Exception as e:
        logger.error(f"Judge error: {e}")
        return None, None
