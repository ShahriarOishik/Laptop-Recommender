from __future__ import annotations

import json

from app.services.artifact_store import ArtifactStore


class SpecificationInsights:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def get(self, item: str | None = None, limit: int = 20) -> list[dict]:
        try:
            path = self.artifacts.ensure("association_rules.json")
        except FileNotFoundError:
            return []
        with path.open("r", encoding="utf-8") as input_file:
            rules = json.load(input_file)
        if item:
            normalized = item.strip().lower()
            rules = [
                rule
                for rule in rules
                if normalized in {str(value).lower() for value in rule.get("antecedent", [])}
            ]
        return rules[:limit]
