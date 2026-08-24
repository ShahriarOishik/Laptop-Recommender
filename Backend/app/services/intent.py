from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import ChatIntent, LaptopRecommendation, SearchFilters
from app.services.conversation_store import ConversationState
from app.services.parser import QueryParser

_ORDINAL_WORDS = {
    "first": 0, "1st": 0,
    "second": 1, "2nd": 1,
    "third": 2, "3rd": 2,
    "fourth": 3, "4th": 3,
    "fifth": 4, "5th": 4,
}
_ORDINAL_PATTERN = re.compile(
    r"\b(?:the\s+)?(" + "|".join(_ORDINAL_WORDS) + r")\b(?:\s+(?:one|option|laptop|choice))?",
    re.I,
)
_OPTION_NUMBER_PATTERN = re.compile(r"\b(?:option|choice|laptop|#)\s*(\d)\b", re.I)
_LAST_ONE_PATTERN = re.compile(r"\bthe\s+last\s+one\b", re.I)
_ALL_PATTERN = re.compile(
    r"\b(?:these|those|all of (?:them|these)|any of (?:them|these)|"
    r"the (?:current )?(?:recommendations|options|laptops))\b",
    re.I,
)
_CHEAPER_PATTERN = re.compile(r"\b(?:cheaper|cheapest|less expensive|lowest price|budget option)\b", re.I)
_PRICIER_PATTERN = re.compile(
    r"\b(?:more expensive|pricier|priciest|most expensive|highest price|premium option)\b", re.I
)

_FOLLOW_UP_CUES = re.compile(
    r"\b(?:why|compare|comparison|vs\.?|versus|which (?:one|is|of)|"
    r"best (?:for|value|overall|choice)|worth it|worth the|trade[\s-]?off|"
    r"pros and cons|advantages?|disadvantages?|downside|drawback|"
    r"value for money|better (?:for|choice|option)|instead of)\b",
    re.I,
)

_RELAXATION_CUES = re.compile(
    r"\b(?:don'?t|do not) care about\b|\bno longer (?:want|need|care)\b|"
    r"\bnot (?:worried|concerned) about\b|\b(?:remove|drop|clear|ignore)\b.*\b(?:requirement|constraint|filter)\b|"
    r"\bany\s+\w+\s+(?:is|will be)\s+fine\b|\bno\s+(?:budget|price|ram|storage|weight)\s+limit\b|"
    r"\bdoesn'?t matter (?:anymore|any more)?\b",
    re.I,
)

_GENERAL_QUESTION_CUES = re.compile(
    r"^(?:what is|what does|what are|explain|define|how does|how do)\b", re.I
)


@dataclass
class IntentResult:
    intent: ChatIntent
    referenced_laptop_ids: list[int] = field(default_factory=list)


def classify(message: str, state: ConversationState, parser: QueryParser) -> IntentResult:
    """Deterministic intent classification, mirroring the regex-driven style
    already used in ``parser.py``. No conversation state / prior
    recommendations means every message is a fresh recommendation request.
    """
    text = (message or "").strip()
    has_prior = bool(state.last_recommendations)

    if not has_prior:
        # A genuine definitional question ("what does dedicated GPU mean?")
        # asked as the very first message should stay a general answer, not
        # trigger a search — checked here because the command gate no
        # longer downgrades first-turn recommendation intents to chat.
        if _GENERAL_QUESTION_CUES.search(text):
            return IntentResult(intent=ChatIntent.GENERAL_QUESTION)
        return IntentResult(intent=ChatIntent.NEW_RECOMMENDATION)

    if _RELAXATION_CUES.search(text):
        return IntentResult(intent=ChatIntent.UPDATED_REQUIREMENTS)

    # Strong reference/comparison signals (ordinals, "the Lenovo", "why...")
    # win before a merely-coincidental filter-looking token (e.g. a brand
    # name in "why did you recommend the Lenovo?") gets read as a new
    # constraint.
    if _FOLLOW_UP_CUES.search(text) or _has_reference_cue(text, state.last_recommendations):
        return IntentResult(
            intent=ChatIntent.FOLLOW_UP,
            referenced_laptop_ids=resolve_references(text, state.last_recommendations),
        )

    parsed_filters = parser.parse(text, None).filters
    changed_fields = {
        name
        for name in parsed_filters.active_fields()
        if getattr(parsed_filters, name) != getattr(state.last_filters, name)
    }
    if changed_fields:
        return IntentResult(intent=ChatIntent.UPDATED_REQUIREMENTS)

    if _GENERAL_QUESTION_CUES.search(text):
        return IntentResult(intent=ChatIntent.GENERAL_QUESTION)

    # Fallback: prefer reusing the existing recommendation context over an
    # unwanted re-search.
    return IntentResult(
        intent=ChatIntent.FOLLOW_UP,
        referenced_laptop_ids=resolve_references(text, state.last_recommendations),
    )


def _has_reference_cue(text: str, recommendations: list[LaptopRecommendation]) -> bool:
    if _ORDINAL_PATTERN.search(text) or _OPTION_NUMBER_PATTERN.search(text):
        return True
    if _ALL_PATTERN.search(text) or _LAST_ONE_PATTERN.search(text):
        return True
    if _CHEAPER_PATTERN.search(text) or _PRICIER_PATTERN.search(text):
        return True
    lower = text.lower()
    for recommendation in recommendations:
        if recommendation.brand and re.search(rf"\b{re.escape(recommendation.brand.lower())}\b", lower):
            return True
    return False


def resolve_references(text: str, recommendations: list[LaptopRecommendation]) -> list[int]:
    """Resolve phrases like 'the first one', 'option 3', 'the Lenovo',
    'the cheaper one', or 'these' to laptop_ids from the current
    recommendation set. Returns [] when nothing specific is referenced
    (caller should treat that as "the whole current set")."""
    if not recommendations:
        return []
    lower = text.lower()
    resolved: list[int] = []

    if _ALL_PATTERN.search(lower):
        return [recommendation.laptop_id for recommendation in recommendations]

    if _LAST_ONE_PATTERN.search(lower):
        resolved.append(recommendations[-1].laptop_id)

    for match in _ORDINAL_PATTERN.finditer(lower):
        index = _ORDINAL_WORDS.get(match.group(1).lower())
        if index is not None and index < len(recommendations):
            laptop_id = recommendations[index].laptop_id
            if laptop_id not in resolved:
                resolved.append(laptop_id)

    for match in _OPTION_NUMBER_PATTERN.finditer(lower):
        index = int(match.group(1)) - 1
        if 0 <= index < len(recommendations):
            laptop_id = recommendations[index].laptop_id
            if laptop_id not in resolved:
                resolved.append(laptop_id)

    priced = [r for r in recommendations if r.price_usd is not None]
    if _CHEAPER_PATTERN.search(lower) and priced:
        laptop_id = min(priced, key=lambda r: r.price_usd).laptop_id
        if laptop_id not in resolved:
            resolved.append(laptop_id)
    if _PRICIER_PATTERN.search(lower) and priced:
        laptop_id = max(priced, key=lambda r: r.price_usd).laptop_id
        if laptop_id not in resolved:
            resolved.append(laptop_id)

    for recommendation in recommendations:
        if recommendation.brand and re.search(rf"\b{re.escape(recommendation.brand.lower())}\b", lower):
            if recommendation.laptop_id not in resolved:
                resolved.append(recommendation.laptop_id)

    return resolved


_FIELD_CLEAR_CUES: dict[str, re.Pattern[str]] = {
    "min_price_usd": re.compile(r"\bno\s+(?:minimum\s+)?(?:budget|price)\s+limit\b", re.I),
    "max_price_usd": re.compile(r"\bno\s+(?:maximum\s+)?(?:budget|price)\s+limit\b|\bany\s+price\s+(?:is|will be)\s+fine\b", re.I),
    "min_ram_gb": re.compile(r"\bno\s+ram\s+(?:limit|requirement)\b|\bany\s+ram\s+(?:is|will be)\s+fine\b", re.I),
    "min_storage_gb": re.compile(r"\bno\s+storage\s+(?:limit|requirement)\b", re.I),
    "min_vram_gb": re.compile(r"\bno\s+vram\s+(?:limit|requirement)\b|\bany\s+vram\s+(?:is|will be)\s+fine\b", re.I),
    "brands": re.compile(r"\bany\s+brand\s+(?:is|will be)\s+fine\b", re.I),
    "gpu_tags": re.compile(r"\bgpu\s+doesn'?t matter\b|\bany\s+gpu\s+(?:is|will be)\s+fine\b", re.I),
}


def cleared_fields(text: str) -> set[str]:
    """Fields whose explicit prior constraint the user asked to drop."""
    return {field for field, pattern in _FIELD_CLEAR_CUES.items() if pattern.search(text)}


_LIST_FIELDS = {
    "brands", "gpu_tags", "excluded_brands", "excluded_gpu_tags",
    "storage_types", "operating_systems",
}


def merge_filters(previous: SearchFilters, new_explicit: SearchFilters, cleared: set[str]) -> SearchFilters:
    """Carry forward locked filters from the prior turn, override with any
    explicitly (re-)stated in the new message, and drop fields the user
    asked to relax."""
    merged = previous.model_dump()
    for name in new_explicit.active_fields():
        merged[name] = getattr(new_explicit, name)
    for name in cleared:
        merged[name] = [] if name in _LIST_FIELDS else None
    return SearchFilters(**merged)
