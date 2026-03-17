"""Research agent: generates new papers using real web search + LLM reasoning.

Uses Claude Agent SDK with WebSearch/WebFetch tools for real evidence gathering.
Uses claude-sonnet-4-6 for high-quality research output.
30% chance of generating a rebuttal paper against the champion.

Prompt design principles:
- Research question is the NORTH STAR, not an afterthought
- Popper: every claim must have falsifiable assumptions with testable boundary conditions
- Bayes: evidence should UPDATE beliefs from existing context, not just confirm
- Lakatos: new predictions > ad hoc patches (especially in rebuttals)
- Build on existing knowledge, don't repeat known ground
"""

import asyncio
import json
import logging

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

from auto_research.agents._sdk import OMC_OPTS, enforce_research_quality
from auto_research.core.memory import save_paper

logger = logging.getLogger("autoresearch.research")

RESEARCH_SYSTEM_PROMPT = """You are a research agent in an evolutionary knowledge ecosystem.
Your mission is to advance collective understanding of a specific research question
by producing a well-evidenced, falsifiable research paper.

## Your North Star
The user's research question defines what matters. Every search query you form,
every source you evaluate, and every claim you make must demonstrably serve
that question. If your paper could have been written without knowing the research
question, you have failed.

## Evidence Gathering Protocol
You have access to WebSearch and WebFetch tools.

1. DECOMPOSE the research question into 2-3 searchable sub-questions
2. Use WebSearch for EACH sub-question (minimum 3 searches, targeting different facets)
3. Use WebFetch to read the most promising sources IN FULL — skim is not enough
4. EVALUATE source quality:
   - Peer-reviewed > technical report > blog post > opinion
   - Recency matters: prefer sources from the last 3 years unless citing foundational work
   - Cross-reference: a claim supported by 2+ independent sources is stronger
5. If the existing context already covers a finding, DO NOT repeat it.
   Your job is to EXTEND the frontier, not restate known ground.

## Paper Requirements
- Your claim MUST be falsifiable (Popper gate): state specific conditions under which
  it would be FALSE. "This works well" is not falsifiable. "This approach reduces latency
  by >30% in single-node deployments with <10GB working sets" IS falsifiable.
- Your assumptions field must list TESTABLE boundary conditions, not vague caveats.
  Bad: "Assumes standard conditions." Good: "Assumes write-heavy workload (>70% writes),
  single-region deployment, and sub-100ms latency requirements."
- Evidence should UPDATE beliefs from the existing context (Bayesian):
  explicitly state what was previously believed and how your evidence changes that.
- If your paper makes predictions beyond your evidence, label them clearly as predictions.

## Building on Existing Knowledge
You will receive a "Current Knowledge Context" section. READ IT CAREFULLY.
- Do NOT repeat claims already established with high fitness.
- Do NOT ignore contradictions or limitations noted in prior annotations.
- DO build on, refine, or challenge existing findings.
- DO explore gaps and unanswered sub-questions.

After gathering evidence, output your paper as a JSON object with these exact keys:
{
  "claim": "One-sentence core claim (must be falsifiable)",
  "l0_summary": "~50 word summary for quick filtering",
  "l1_summary": "~500 word detailed summary including: what was previously known, what new evidence you found, and how it changes understanding",
  "l2_content": "Full paper content (1000-2000 words) with clear sections: Background, Evidence, Analysis, Limitations, Predictions",
  "evidence_sources": [{"title": "...", "url": "...", "excerpt": "key finding quoted"}],
  "assumptions": "Specific, testable boundary conditions as a bullet list",
  "topic_tag": "the_topic_tag",
  "perspective": "empirical|theoretical|applied|critical"
}

IMPORTANT: Your final message must contain ONLY the JSON object, no other text."""

REBUTTAL_ADDITION = """

SPECIAL INSTRUCTION: You are writing a REBUTTAL paper.

## Champion's Position
The current champion claims: "{champion_claim}"

## Your Rebuttal Mission
1. Search for evidence that CONTRADICTS, LIMITS, or SUPERSEDES this claim
2. You MUST propose an ALTERNATIVE claim, not just point out flaws
   (Lakatos criterion: your rebuttal must be a PROGRESSIVE research program
   that makes NEW testable predictions the champion cannot make)
3. Your paper must answer: "If the champion is wrong/limited, what is the
   BETTER explanation, and what NEW prediction does it make?"

ANTI-PATTERNS TO AVOID:
- "The champion is wrong because [one exception]" — this is a DEGENERATIVE patch
- "More research is needed" — this is not a claim
- Repeating the champion's framework with minor modifications

Choose a different perspective than the champion if possible.
Explicitly state in your 'assumptions' field the conditions under which the
champion's claim WOULD hold vs. conditions under which YOUR claim is superior."""


async def run_research(
    conn,
    topic: str,
    session_id: str,
    context: str,
    champion_claim: str = None,
    is_rebuttal: bool = False,
    research_question: str = "",
) -> dict:
    """Generate a new research paper using Claude Agent SDK with real web search.

    Args:
        conn: SQLite connection.
        topic: Research topic tag.
        session_id: Current session ID.
        context: Session context from build_session_context().
        champion_claim: Champion's claim (for rebuttals).
        is_rebuttal: Whether to generate a rebuttal paper.
        research_question: Detailed research question from the user.

    Returns:
        Paper dict with all required fields + 'id' key.
    """
    system = RESEARCH_SYSTEM_PROMPT
    if is_rebuttal and champion_claim:
        system += REBUTTAL_ADDITION.format(champion_claim=champion_claim)

    # Build the research question section
    question_section = ""
    if research_question:
        question_section = f"""
## Research Question (항상 이 질문을 염두에 두고 연구하세요)
{research_question}
"""

    user_prompt = f"""## Research Mission
Topic: {topic}
{question_section}
## Current Knowledge Context
{context}

## Your Task
1. ANALYZE the context above: What is well-established? What is contradicted?
   What gaps remain relative to the research question?
2. CHOOSE a gap or unresolved tension to investigate
3. SEARCH the web for evidence that addresses this specific gap
4. WRITE a paper that ADVANCES the ecosystem's knowledge beyond its current state

Do NOT produce a paper that merely restates what the context already covers.
Your paper will be compared against existing papers — redundancy loses."""

    logger.info(f"Generating {'rebuttal' if is_rebuttal else 'new'} paper on topic: {topic}")
    logger.debug(f"=== RESEARCH AGENT SYSTEM PROMPT ===\n{system}")
    logger.debug(f"=== RESEARCH AGENT USER PROMPT ===\n{user_prompt}")

    try:
        result_text = ""
        async for message in query(
            prompt=user_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["WebSearch", "WebFetch"],
                permission_mode="bypassPermissions",
                system_prompt=system,
                model="claude-sonnet-4-6",
                max_turns=15,
                hooks={
                    "Stop": [HookMatcher(matcher="*", hooks=[enforce_research_quality])]
                },
                **OMC_OPTS,
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
            # Log intermediate messages for debugging
            elif hasattr(message, "content") and message.content:
                for block in message.content:
                    if hasattr(block, "name"):
                        logger.debug(f"Tool used: {block.name}")

        result_text = result_text.strip()
        logger.debug(f"=== RESEARCH AGENT RAW RESULT ({len(result_text)} chars) ===\n{result_text[:3000]}")

        # Try to extract JSON from the response
        paper = _parse_paper_json(result_text, topic)

        # Save to database
        pid = save_paper(conn, paper)
        paper["id"] = pid

        logger.info(f"Paper generated: {pid} - {paper['claim'][:80]}")
        return paper

    except Exception as e:
        logger.error(f"Research agent error: {e}")
        # Generate a minimal fallback paper
        paper = {
            "claim": f"Research on {topic} requires further investigation.",
            "l0_summary": f"Preliminary findings on {topic}.",
            "l1_summary": f"An initial exploration of {topic}. Error during generation: {str(e)[:200]}",
            "l2_content": f"This paper was generated as a fallback due to an error: {str(e)[:500]}",
            "evidence_sources": [],
            "assumptions": "This is a placeholder paper.",
            "topic_tag": topic,
            "perspective": "empirical",
        }
        pid = save_paper(conn, paper)
        paper["id"] = pid
        return paper


def _parse_paper_json(text: str, topic: str) -> dict:
    """Parse LLM output into a paper dict, with fallback handling."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        paper = json.loads(text)

        required = ["claim", "l0_summary", "l1_summary", "l2_content"]
        for field in required:
            if field not in paper or not paper[field]:
                paper[field] = f"[Missing {field}]"

        paper.setdefault("evidence_sources", [])
        paper.setdefault("assumptions", "None stated")
        paper.setdefault("topic_tag", topic)
        paper.setdefault("perspective", "empirical")

        valid_perspectives = {"empirical", "theoretical", "applied", "critical"}
        if paper["perspective"] not in valid_perspectives:
            paper["perspective"] = "empirical"

        return paper

    except (json.JSONDecodeError, IndexError, KeyError):
        return {
            "claim": text[:200] if text else f"Research on {topic}",
            "l0_summary": text[:100] if text else f"Study on {topic}",
            "l1_summary": text[:1000] if text else f"Detailed study on {topic}",
            "l2_content": text or f"Full content on {topic}",
            "evidence_sources": [],
            "assumptions": "Parsed from unstructured output",
            "topic_tag": topic,
            "perspective": "empirical",
        }
