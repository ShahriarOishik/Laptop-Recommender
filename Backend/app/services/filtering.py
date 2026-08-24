from __future__ import annotations

from dataclasses import dataclass

from app.models import SearchFilters


@dataclass(frozen=True)
class FilterPass:
    level: int
    name: str
    filters: SearchFilters
    active_fields: frozenset[str]
    relaxed_fields: tuple[str, ...]


PREFERENCE_FIELDS = {
    "brands",
    "storage_types",
    "operating_systems",
    "max_weight_kg",
    "min_weight_kg",
}
MAIN_REQUIREMENTS = {
    "min_price_usd",
    "max_price_usd",
    "min_ram_gb",
    "min_storage_gb",
    "min_vram_gb",
    "gpu_tags",
}
CORE_REQUIREMENTS = {
    "min_price_usd",
    "max_price_usd",
}


def build_filter_passes(
    filters: SearchFilters,
    locked_fields: set[str],
    allow_relaxation: bool = True,
) -> list[FilterPass]:
    all_fields = filters.active_fields()
    if not all_fields:
        return [
            FilterPass(
                level=1,
                name="no_metadata_constraints",
                filters=filters,
                active_fields=frozenset(),
                relaxed_fields=(),
            )
        ]

    candidates = [("strict", all_fields)]
    if allow_relaxation:
        candidates.extend(
            [
                ("preferences_relaxed", (all_fields - PREFERENCE_FIELDS) | locked_fields),
                ("main_requirements", (all_fields & MAIN_REQUIREMENTS) | locked_fields),
                ("core_requirements", (all_fields & CORE_REQUIREMENTS) | locked_fields),
                ("locked_only", all_fields & locked_fields),
            ]
        )
    passes: list[FilterPass] = []
    seen: set[frozenset[str]] = set()
    for name, fields in candidates:
        active = frozenset(fields & all_fields)
        if active in seen:
            continue
        seen.add(active)
        passes.append(
            FilterPass(
                level=len(passes) + 1,
                name=name,
                filters=filters.subset(set(active)),
                active_fields=active,
                relaxed_fields=tuple(sorted(all_fields - active)),
            )
        )
    return passes
