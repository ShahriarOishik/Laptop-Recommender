from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

import numpy as np


@dataclass
class CacheEntry:
    namespace: str
    embedding: np.ndarray
    value: Any


class SemanticCache:
    def __init__(self, max_entries: int, similarity_threshold: float) -> None:
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self._entries: OrderedDict[int, CacheEntry] = OrderedDict()
        self._next_id = 0
        self._hits = 0
        self._misses = 0
        self._lock = RLock()

    def get(self, namespace: str, embedding: np.ndarray) -> Any | None:
        vector = self._normalized(embedding)
        with self._lock:
            best_id: int | None = None
            best_score = -1.0
            for entry_id, entry in self._entries.items():
                if entry.namespace != namespace:
                    continue
                score = float(vector @ entry.embedding)
                if score > best_score:
                    best_id, best_score = entry_id, score
            if best_id is not None and best_score >= self.similarity_threshold:
                self._hits += 1
                self._entries.move_to_end(best_id)
                return deepcopy(self._entries[best_id].value)
            self._misses += 1
            return None

    def put(self, namespace: str, embedding: np.ndarray, value: Any) -> None:
        with self._lock:
            self._entries[self._next_id] = CacheEntry(
                namespace=namespace,
                embedding=self._normalized(embedding),
                value=deepcopy(value),
            )
            self._next_id += 1
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }

    @staticmethod
    def _normalized(embedding: np.ndarray) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector
