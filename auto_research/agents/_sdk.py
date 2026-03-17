"""Shared Claude Agent SDK configuration for OMC plugin integration.

Provides:
1. OMC plugin path discovery and shared options
2. Quality-enforcement Stop hooks (mini-ralph pattern)
   - Each agent gets a Stop hook that checks output quality
   - If quality is insufficient, the hook blocks the stop and tells the agent to keep working
   - This is the SDK equivalent of OMC's persistent-mode.cjs
"""

import glob
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("autoresearch.sdk")


# --- OMC Plugin Discovery ---

def _find_omc_plugin_path() -> str:
    """Dynamically discover the oh-my-claudecode plugin path."""
    env_path = os.environ.get("OMC_PLUGIN_PATH")
    if env_path and os.path.isdir(os.path.expanduser(env_path)):
        return os.path.expanduser(env_path)

    base = os.path.expanduser("~/.claude/plugins/cache/omc/oh-my-claudecode")
    if os.path.isdir(base):
        versions = sorted(glob.glob(os.path.join(base, "*")), reverse=True)
        if versions and os.path.isdir(versions[0]):
            return versions[0]

    return ""


OMC_PLUGIN_PATH = _find_omc_plugin_path()

# Shared options for research agent (the only agent that benefits from OMC tools)
OMC_OPTS = dict(
    setting_sources=["user", "project"],
    plugins=[{"type": "local", "path": OMC_PLUGIN_PATH}] if OMC_PLUGIN_PATH else [],
)


# --- Quality-Enforcement Stop Hooks (Mini-Ralph Pattern) ---
#
# These hooks fire when the agent tries to stop.
# If the output quality is insufficient, they block the stop
# and instruct the agent to keep working.
#
# This is the Python equivalent of OMC's persistent-mode.cjs:
#   OMC:     Stop hook → shell script → "Work is NOT done. Continue."
#   Our SDK: Stop hook → Python callback → "품질 미달. 계속 연구해."


# Track retry counts per agent to avoid infinite loops
_stop_attempt_counts = {}
MAX_STOP_RETRIES = 3  # Allow up to 3 quality rejections, then let through


async def enforce_research_quality(input_data, tool_use_id, context):
    """Research agent Stop hook: enforce paper quality before allowing completion.

    Checks:
    1. Result contains actual JSON with required fields
    2. Evidence sources are present (not empty)
    3. Assumptions are specific (not placeholder)
    4. Content has sufficient depth
    """
    key = "research"
    _stop_attempt_counts.setdefault(key, 0)
    _stop_attempt_counts[key] += 1

    # Safety valve: after MAX_STOP_RETRIES rejections, let through
    if _stop_attempt_counts[key] > MAX_STOP_RETRIES:
        logger.info(f"Research quality hook: max retries ({MAX_STOP_RETRIES}) reached, allowing stop")
        _stop_attempt_counts[key] = 0
        return {}

    result = input_data.get("result", "")
    if not result:
        return {}  # No result to check

    # Check 1: Has actual content (not too short)
    if len(result) < 300:
        logger.info("Research quality hook: result too short, blocking stop")
        return {
            "decision": "block",
            "reason": "논문이 너무 짧습니다. WebSearch로 더 검색하고, "
                      "근거를 보강한 완전한 논문을 작성하세요. "
                      "JSON 형식으로 claim, l0_summary, l1_summary, l2_content, "
                      "evidence_sources, assumptions를 모두 포함해야 합니다."
        }

    # Check 2: Has evidence (not empty)
    if '"evidence_sources": []' in result or '"evidence_sources":[]' in result:
        logger.info("Research quality hook: no evidence sources, blocking stop")
        return {
            "decision": "block",
            "reason": "증거가 없습니다! WebSearch와 WebFetch를 사용해서 "
                      "실제 연구 논문, 기술 문서, 벤치마크 결과를 찾으세요. "
                      "최소 2개 이상의 실제 출처가 필요합니다."
        }

    # Check 3: Has specific assumptions (not placeholder)
    weak_assumptions = [
        '"assumptions": "None stated"',
        '"assumptions": ""',
        '"assumptions": "N/A"',
        '"assumptions": "This is a placeholder',
    ]
    for weak in weak_assumptions:
        if weak in result:
            logger.info("Research quality hook: weak assumptions, blocking stop")
            return {
                "decision": "block",
                "reason": "Popper 반증 가능성 게이트 미충족! "
                          "구체적이고 테스트 가능한 가정을 명시하세요. "
                          "예: '이 주장은 단일 노드 환경에서 메모리 <10GB일 때만 유효하다'"
            }

    # All checks passed
    logger.info("Research quality hook: quality sufficient, allowing stop")
    _stop_attempt_counts[key] = 0
    return {}


async def enforce_comparison_quality(input_data, tool_use_id, context):
    """Compare agent Stop hook: ensure classification/judgment produced a clear result."""
    key = "compare"
    _stop_attempt_counts.setdefault(key, 0)
    _stop_attempt_counts[key] += 1

    if _stop_attempt_counts[key] > MAX_STOP_RETRIES:
        _stop_attempt_counts[key] = 0
        return {}

    result = input_data.get("result", "")
    if not result:
        return {}

    # For classifier: must contain one of the three categories
    result_lower = result.lower()
    has_classification = any(w in result_lower for w in ("opposing", "complementary", "orthogonal"))
    has_judgment = '"winner"' in result

    if not has_classification and not has_judgment:
        logger.info("Compare quality hook: no clear classification or judgment, blocking stop")
        return {
            "decision": "block",
            "reason": "분류 또는 판정 결과가 명확하지 않습니다. "
                      "반드시 opposing/complementary/orthogonal 중 하나로 분류하거나, "
                      '{\"winner\": \"A\" or \"B\", \"reasoning\": \"...\"} 형식으로 판정하세요.'
        }

    _stop_attempt_counts[key] = 0
    return {}


async def enforce_reflection_quality(input_data, tool_use_id, context):
    """Reflector agent Stop hook: ensure annotations are actionable, not generic."""
    key = "reflector"
    _stop_attempt_counts.setdefault(key, 0)
    _stop_attempt_counts[key] += 1

    if _stop_attempt_counts[key] > MAX_STOP_RETRIES:
        _stop_attempt_counts[key] = 0
        return {}

    result = input_data.get("result", "")
    if not result:
        return {}

    # Must be a JSON array with content
    if "[" not in result or '"content"' not in result:
        logger.info("Reflection quality hook: not a valid annotation array, blocking stop")
        return {
            "decision": "block",
            "reason": "유효한 annotation JSON 배열을 출력하세요. "
                      '[{"content": "구체적 인사이트", "tags": ["tag"], '
                      '"suggested_search": "다음 검색어"}] 형식이어야 합니다.'
        }

    # Check for generic/lazy annotations
    generic_phrases = ["more research is needed", "추가 연구가 필요", "further investigation"]
    for phrase in generic_phrases:
        if phrase.lower() in result.lower():
            logger.info("Reflection quality hook: generic annotation detected, blocking stop")
            return {
                "decision": "block",
                "reason": "'추가 연구가 필요'는 너무 모호합니다. "
                          "구체적으로 무엇을 연구해야 하는지, 어떤 검색어로 찾을 수 있는지, "
                          "어떤 조건에서 현재 발견이 한계를 보이는지 명시하세요."
            }

    _stop_attempt_counts[key] = 0
    return {}
