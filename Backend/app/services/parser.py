from __future__ import annotations

import re

from app.models import ParsedQuery, SearchFilters


class QueryParser:
    BRANDS = {
        "acer", "apple", "asus", "aorus", "dell", "dynabook", "fujitsu",
        "gigabyte", "google", "honor", "hp", "huawei", "lenovo", "lg",
        "medion", "microsoft", "msi", "razer", "samsung", "schenker",
        "toshiba", "xiaomi",
    }
    SEMANTIC_TERMS = (
        "gaming", "student", "programming", "office", "business", "creative",
        "video editing", "long battery life", "lightweight", "quiet",
        "comfortable keyboard", "professional", "portable", "powerful",
    )
    STRONG_WORDS = re.compile(r"\b(must|must have|required|only|non-negotiable)\b", re.I)
    # Guards price-amount regexes against matching a bare number that is
    # actually a RAM/storage/weight/etc. quantity, e.g. "at least 16GB RAM"
    # should not also set a $16 minimum price.
    _NOT_PRICE_UNIT = (
        r"(?!\s*(?:gb|tb|mb|kgs?|lbs?|g\b|inch(?:es)?|in\b|hz|mhz|ghz|"
        r"w\b|wh|mp|nits?|hours?|hrs?|cores?|threads?)\b)"
    )
    # A well-formed number: leading digit, then digits/commas, then at most
    # one decimal point. `[\d,.]+` (the old pattern) matches any run of
    # digits/commas/dots — including malformed input like "1000.." from a
    # sentence-ending period right after a price — which then crashes
    # float() in _number(). This can't capture more than one ".". The
    # trailing `+` on the optional decimal group makes it possessive: once
    # decided, the engine won't backtrack out of it to satisfy a later part
    # of the pattern — without that, "at least 1.2 kg" could backtrack the
    # captured number down to just "1" (dropping ".2") to dodge the
    # _NOT_PRICE_UNIT check, misreading it as a $1 price.
    _PRICE_NUMBER = r"\d[\d,]*(?:\.\d+)?+"

    def __init__(self, range_statistics: dict[str, dict[str, float]] | None = None) -> None:
        self.range_statistics = range_statistics or {}

    def parse(self, query: str | None, ui_filters: SearchFilters | None = None) -> ParsedQuery:
        text = " ".join((query or "").strip().split())
        lower = text.lower()
        values: dict[str, object] = {}
        locked: set[str] = set()
        warnings: list[str] = []

        self._parse_price(lower, values, locked)
        self._parse_memory(lower, values, locked)
        self._parse_weight(lower, values, locked)
        self._parse_gpu(lower, values, locked)
        self._parse_brand(lower, values, locked)
        self._parse_storage_type(lower, values, locked)
        self._parse_os(lower, values, locked)

        if re.search(r"\b(around|roughly|approximately|about)\s*\$?\s*[\d,.]+", lower):
            warnings.append("An approximate budget was kept as a semantic preference, not a strict filter.")

        parsed_filters = SearchFilters(**values)
        if ui_filters:
            merged = parsed_filters.model_dump()
            for field in ui_filters.active_fields():
                merged[field] = getattr(ui_filters, field)
            parsed_filters = SearchFilters(**merged)
            locked.update(ui_filters.active_fields())

        inferred_filters = self._infer_soft_ranges(parsed_filters)
        if inferred_filters.min_price_usd is not None:
            warnings.append("Inferred a soft minimum price from the requested maximum price.")
        if inferred_filters.max_price_usd is not None:
            warnings.append("Inferred a soft maximum price from the requested minimum price.")
        if inferred_filters.min_weight_kg is not None:
            warnings.append("Inferred a soft minimum weight from the requested maximum weight.")
        if inferred_filters.max_weight_kg is not None:
            warnings.append("Inferred a soft maximum weight from the requested minimum weight.")

        semantic_query = self._semantic_query(text) if text else ""
        semantic_lower = semantic_query.lower()
        semantic_constraints = [term for term in self.SEMANTIC_TERMS if term in semantic_lower]
        embedding_query = self._embedding_query(semantic_query, parsed_filters)
        return ParsedQuery(
            original_query=text,
            semantic_query=semantic_query,
            embedding_query=embedding_query,
            semantic_constraints=semantic_constraints,
            filters=parsed_filters,
            inferred_filters=inferred_filters,
            locked_fields=locked,
            confidence=0.95 if parsed_filters.active_fields() else 0.85,
            warnings=warnings,
        )

    def _semantic_query(self, text: str) -> str:
        """Remove structured constraints before the text is embedded."""
        semantic = text
        patterns = (
            r"\b(?:between|from)\s*\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?\s*"
            r"(?:and|to|-)\s*\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?",
            r"\b(?:around|roughly|approximately|about)\s*\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?",
            r"\b(?:under|below|less than|at most|no more than|up to|over|above|more than)\s*"
            r"\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?",
            r"\b(?:minimum|max(?:imum)?|budget(?: of)?)\s*\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?",
            r"\bbudget(?:\s+is|\s+of|'?s)?\s*(?:actually\s*)?:?\s*\$?\s*[\d,.]+\s*(?:k|usd|dollars?)?",
            r"\b(?:at least|minimum|min(?:imum)?(?: of)?|with)\s*\d+(?:\.\d+)?\s*"
            r"(?:gb|tb)\s*(?:of\s*)?(?:ram|memory|vram|storage|ssd|hdd)?",
            r"\b\d+(?:\.\d+)?\s*(?:gb|tb)\s*(?:ram|memory|vram|storage|ssd|hdd)\b",
            r"\b(?:under|below|less than|at most)\s*\d+(?:\.\d+)?\s*kg\b",
            r"\b(?:over|above|more than|at least|minimum|min(?:imum)?(?: of)?)\s*"
            r"\d+(?:\.\d+)?\s*kg\b",
            r"\b(?:rtx|gtx|radeon|rx|arc)\s*\d{0,4}\w*\s*(?:graphics|gpu)?\b",
            r"\b(?:ssd|nvme|hdd)\b",
            r"\b(?:windows|linux|macos|chrome\s+os)\b",
        )
        for pattern in patterns:
            semantic = re.sub(pattern, " ", semantic, flags=re.I)
        for brand in self.BRANDS:
            semantic = re.sub(rf"\b{re.escape(brand)}\b", " ", semantic, flags=re.I)
        semantic = re.sub(r"\s+", " ", semantic).strip(" ,;:-")
        semantic = re.sub(
            r"\b(?:and|with|that|which|must|required|only)\s*$", "", semantic, flags=re.I
        ).strip(" ,;:-")
        return semantic or "laptop recommendation"

    @staticmethod
    def _embedding_query(
        semantic_query: str,
        filters: SearchFilters,
        inferred_filters: SearchFilters | None = None,
    ) -> str:
        constraints = QueryParser._filter_text(filters)
        if inferred_filters:
            constraints.extend(
                "soft preference " + value
                for value in QueryParser._filter_text(inferred_filters)
            )
        if not constraints:
            return semantic_query
        prefix = semantic_query or "laptop recommendation"
        return prefix + ". Structured constraints: " + "; ".join(constraints) + "."

    @staticmethod
    def _filter_text(filters: SearchFilters) -> list[str]:
        constraints: list[str] = []
        if filters.min_price_usd is not None:
            constraints.append(f"minimum price {filters.min_price_usd:g} USD")
        if filters.max_price_usd is not None:
            constraints.append(f"maximum price {filters.max_price_usd:g} USD")
        if filters.min_ram_gb is not None:
            constraints.append(f"at least {filters.min_ram_gb:g} GB RAM")
        if filters.min_storage_gb is not None:
            constraints.append(f"at least {filters.min_storage_gb:g} GB storage")
        if filters.min_vram_gb is not None:
            constraints.append(f"at least {filters.min_vram_gb:g} GB VRAM")
        if filters.min_weight_kg is not None:
            constraints.append(f"minimum weight {filters.min_weight_kg:g} kg")
        if filters.max_weight_kg is not None:
            constraints.append(f"maximum weight {filters.max_weight_kg:g} kg")
        if filters.brands:
            constraints.append("brands " + ", ".join(filters.brands))
        if filters.gpu_tags:
            constraints.append("GPU " + ", ".join(filters.gpu_tags))
        if filters.excluded_brands:
            constraints.append("exclude brands " + ", ".join(filters.excluded_brands))
        if filters.excluded_gpu_tags:
            constraints.append("exclude GPUs " + ", ".join(filters.excluded_gpu_tags))
        if filters.storage_types:
            constraints.append("storage " + ", ".join(filters.storage_types))
        if filters.operating_systems:
            constraints.append("operating system " + ", ".join(filters.operating_systems))
        return constraints

    def _infer_soft_ranges(self, filters: SearchFilters) -> SearchFilters:
        inferred: dict[str, float] = {}
        for field, lower_field, upper_field in (
            ("price_usd", "min_price_usd", "max_price_usd"),
            ("weight_kg", "min_weight_kg", "max_weight_kg"),
        ):
            stats = self.range_statistics.get(field, {})
            spread = stats.get("robust_std", stats.get("std"))
            if spread is None or spread <= 0:
                continue
            observed_min = stats.get("min", 0.0)
            observed_max = stats.get("max")
            maximum = getattr(filters, upper_field)
            minimum = getattr(filters, lower_field)
            if maximum is not None and minimum is None:
                value = max(observed_min, maximum - spread)
                inferred[lower_field] = min(value, maximum)
            elif minimum is not None and maximum is None and observed_max is not None:
                value = min(observed_max, minimum + spread)
                inferred[upper_field] = max(value, minimum)
        return SearchFilters(**inferred)

    def _lock_if_strong(self, text: str, match: re.Match[str], field: str, locked: set[str]) -> None:
        context = text[max(0, match.start() - 30): match.end() + 30]
        if self.STRONG_WORDS.search(context):
            locked.add(field)

    @staticmethod
    def _is_negated(text: str, match: re.Match[str]) -> bool:
        prefix = text[max(0, match.start() - 16): match.start()]
        return bool(
            re.search(
                r"\b(?:without|no|exclude|excluding)\s*(?:an?\s+)?$|"
                r"\bnot\s+(?:be\s+|an?\s+)?$",
                prefix,
            )
        )

    def _parse_price(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        between = re.search(
            rf"(?:between|from)\s*\$?\s*({self._PRICE_NUMBER})\s*(?:usd|dollars?)?\s*"
            rf"(?:and|to|-)\s*\$?\s*({self._PRICE_NUMBER})",
            text,
        )
        if between:
            values["min_price_usd"] = self._number(between.group(1))
            values["max_price_usd"] = self._number(between.group(2))
            self._lock_if_strong(text, between, "min_price_usd", locked)
            self._lock_if_strong(text, between, "max_price_usd", locked)
            return

        maximum = re.search(
            r"(?:under|below|less than|at most|no more than|max(?:imum)?(?: budget)?(?: of)?|up to)\s*"
            rf"\$?\s*({self._PRICE_NUMBER})(?![\d,])\s*{self._NOT_PRICE_UNIT}(k\b)?",
            text,
        )
        if maximum:
            amount = self._number(maximum.group(1)) * (1000 if maximum.group(2) else 1)
            values["max_price_usd"] = amount
            self._lock_if_strong(text, maximum, "max_price_usd", locked)

        minimum = re.search(
            r"(?:over|above|more than|at least|min(?:imum)?(?: budget)?(?: of)?)\s*"
            rf"\$?\s*({self._PRICE_NUMBER})(?![\d,])\s*{self._NOT_PRICE_UNIT}(k\b)?(?:\s*(?:usd|dollars?))?",
            text,
        )
        if minimum:
            amount = self._number(minimum.group(1)) * (1000 if minimum.group(2) else 1)
            values["min_price_usd"] = amount
            self._lock_if_strong(text, minimum, "min_price_usd", locked)

        if "max_price_usd" not in values and "min_price_usd" not in values:
            stated_budget = re.search(
                rf"\bbudget(?:\s+is|\s+of|'?s)?\s*(?:actually\s*)?:?\s*\$?\s*({self._PRICE_NUMBER})"
                rf"(?![\d,])\s*{self._NOT_PRICE_UNIT}(k\b)?",
                text,
            )
            if stated_budget:
                amount = self._number(stated_budget.group(1)) * (1000 if stated_budget.group(2) else 1)
                values["max_price_usd"] = amount
                self._lock_if_strong(text, stated_budget, "max_price_usd", locked)

    def _parse_memory(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        ram = re.search(
            r"(?:at least|minimum|min(?:imum)?(?: of)?|with)\s*(\d+(?:\.\d+)?)\s*gb\s*(?:of\s*)?ram|"
            r"(\d+(?:\.\d+)?)\s*gb\s*ram(?:\s*(?:or more|minimum))?",
            text,
        )
        if ram:
            values["min_ram_gb"] = float(ram.group(1) or ram.group(2))
            self._lock_if_strong(text, ram, "min_ram_gb", locked)

        storage = re.search(
            r"(?:at least|minimum|min(?:imum)?(?: of)?|with)\s*(\d+(?:\.\d+)?)\s*(tb|gb)\s*(?:of\s*)?(?:storage|ssd|hdd)|"
            r"(\d+(?:\.\d+)?)\s*(tb|gb)\s*(?:storage|ssd|hdd)",
            text,
        )
        if storage:
            amount = float(storage.group(1) or storage.group(3))
            unit = storage.group(2) or storage.group(4)
            values["min_storage_gb"] = amount * 1024 if unit == "tb" else amount
            self._lock_if_strong(text, storage, "min_storage_gb", locked)

        vram = re.search(
            r"(?:at least|minimum|min(?:imum)?(?: of)?|with)\s*(\d+(?:\.\d+)?)\s*gb\s*(?:of\s*)?vram|"
            r"(\d+(?:\.\d+)?)\s*gb\s*vram(?:\s*(?:or more|minimum))?",
            text,
        )
        if vram:
            values["min_vram_gb"] = float(vram.group(1) or vram.group(2))
            self._lock_if_strong(text, vram, "min_vram_gb", locked)

    def _parse_weight(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        maximum = re.search(
            r"(?:under|below|less than|at most)\s*(\d+(?:\.\d+)?)\s*kg", text
        )
        if maximum:
            values["max_weight_kg"] = float(maximum.group(1))
            self._lock_if_strong(text, maximum, "max_weight_kg", locked)
        minimum = re.search(
            r"(?:over|above|more than|at least|minimum|min(?:imum)?(?: of)?)\s*"
            r"(\d+(?:\.\d+)?)\s*kg",
            text,
        )
        if minimum:
            values["min_weight_kg"] = float(minimum.group(1))
            self._lock_if_strong(text, minimum, "min_weight_kg", locked)

    def _parse_gpu(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        exact_matches = list(re.finditer(r"\b(?:rtx|gtx|rx)\s*\d{3,4}\w*\b", text))
        matches = exact_matches or list(re.finditer(r"\b(?:rtx|gtx|radeon|rx|arc)\b", text))
        included: list[str] = []
        excluded: list[str] = []
        for match in matches:
            tag = re.sub(r"\s+", " ", match.group(0))
            if self._is_negated(text, match):
                excluded.append(tag)
                locked.add("excluded_gpu_tags")
            else:
                included.append(tag)
                self._lock_if_strong(text, match, "gpu_tags", locked)
        if included:
            values["gpu_tags"] = list(dict.fromkeys(included))
        if excluded:
            values["excluded_gpu_tags"] = list(dict.fromkeys(excluded))

    def _parse_brand(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        included: list[str] = []
        excluded: list[str] = []
        for brand in sorted(self.BRANDS):
            match = re.search(rf"\b{re.escape(brand)}\b", text)
            if not match:
                continue
            if self._is_negated(text, match):
                excluded.append(brand)
                locked.add("excluded_brands")
            else:
                included.append(brand)
                self._lock_if_strong(text, match, "brands", locked)
        if included:
            values["brands"] = included
        if excluded:
            values["excluded_brands"] = excluded

    def _parse_storage_type(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        types = [kind for kind in ("ssd", "nvme", "hdd") if re.search(rf"\b{kind}\b", text)]
        if types:
            values["storage_types"] = types
            match = re.search(r"\b(?:ssd|nvme|hdd)\b", text)
            if match:
                self._lock_if_strong(text, match, "storage_types", locked)

    def _parse_os(self, text: str, values: dict[str, object], locked: set[str]) -> None:
        aliases = {"windows": "windows", "linux": "linux", "macos": "macos", "chrome os": "chrome os"}
        systems = [normalized for phrase, normalized in aliases.items() if phrase in text]
        if systems:
            values["operating_systems"] = systems
            match = re.search(r"\b(?:windows|linux|macos|chrome os)\b", text)
            if match:
                self._lock_if_strong(text, match, "operating_systems", locked)

    @staticmethod
    def _number(value: str) -> float:
        return float(value.replace(",", ""))
