from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

import faiss
import httpx
import numpy as np

from app.config import Settings
from app.models import IndexType
from app.services.artifact_store import ArtifactStore


@dataclass(frozen=True)
class VectorHit:
    vector_id: int
    similarity: float


class FaissIndexManager:
    def __init__(self, settings: Settings, artifacts: ArtifactStore) -> None:
        self.settings = settings
        self.artifacts = artifacts
        self._indexes: OrderedDict[str, object] = OrderedDict()
        self._lock = RLock()
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        try:
            path = self.artifacts.ensure("index_manifest.json")
        except (FileNotFoundError, httpx.HTTPError):
            return {}
        with path.open("r", encoding="utf-8") as manifest_file:
            return json.load(manifest_file)

    def load_default(self) -> None:
        index_type = IndexType(self.settings.default_index)
        self._get_index(index_type, laptop=True)
        self._get_index(index_type)

    def available(self, index_type: IndexType) -> bool:
        filename = self.settings.index_files[index_type.value]
        try:
            self.artifacts.ensure(filename)
            return True
        except (FileNotFoundError, httpx.HTTPError):
            return False

    def threshold_for(self, index_type: IndexType) -> float:
        thresholds = self._manifest.get("similarity_thresholds", {})
        return float(thresholds.get(index_type.value, self.settings.default_similarity_threshold))

    @property
    def manifest(self) -> dict:
        return self._manifest

    @property
    def ready(self) -> bool:
        return bool(self._indexes)

    def search(
        self,
        index_type: IndexType,
        query_vector: np.ndarray,
        k: int,
        nprobe: int,
        ef_search: int,
        *,
        laptop: bool = False,
    ) -> list[VectorHit]:
        query = np.ascontiguousarray(query_vector.reshape(1, -1), dtype=np.float32)
        if query.shape[1] != self.settings.embedding_dimension:
            raise ValueError(
                f"Query dimension {query.shape[1]} does not match configured dimension "
                f"{self.settings.embedding_dimension}."
            )
        with self._lock:
            index = self._get_index(index_type, laptop=laptop)
            inner = self._inner_index(index)
            if index_type in {IndexType.IVF_FLAT, IndexType.IVF_PQ}:
                inner.nprobe = nprobe
            elif index_type == IndexType.HNSW:
                inner.hnsw.efSearch = ef_search
            scores, ids = index.search(query, k)
        raw_hits = [
            VectorHit(vector_id=int(vector_id), similarity=float(score))
            for score, vector_id in zip(scores[0], ids[0])
            if int(vector_id) >= 0
        ]
        normalized_scores = self._normalized_scores(index, query[0], [hit.vector_id for hit in raw_hits])
        if normalized_scores is None:
            return [
                VectorHit(vector_id=hit.vector_id, similarity=float(np.clip(hit.similarity, -1.0, 1.0)))
                for hit in raw_hits
            ]
        return sorted(
            [
                VectorHit(vector_id=hit.vector_id, similarity=normalized_scores[hit.vector_id])
                for hit in raw_hits
            ],
            key=lambda hit: hit.similarity,
            reverse=True,
        )

    def search_constrained(
        self,
        index_type: IndexType,
        query_vector: np.ndarray,
        allowed_ids: list[int],
        k: int,
        nprobe: int,
        ef_search: int,
        *,
        laptop: bool = False,
    ) -> list[VectorHit]:
        """Rank only metadata-approved vectors without global-top-k leakage.

        FAISS selectors are not consistently supported through every persisted
        IndexIDMap2/index-family combination. Reconstructing the approved IDs
        keeps the hard-filter guarantee correct for all five index types. PQ
        uses its reconstructed (quantized) vectors, matching its approximate
        representation.
        """
        if not allowed_ids or k <= 0:
            return []
        query = np.ascontiguousarray(query_vector.reshape(-1), dtype=np.float32)
        if query.size != self.settings.embedding_dimension:
            raise ValueError(
                f"Query dimension {query.size} does not match configured dimension "
                f"{self.settings.embedding_dimension}."
            )

        with self._lock:
            index = self._get_index(index_type, laptop=laptop)
            vector_ids = list(dict.fromkeys(int(value) for value in allowed_ids))
            try:
                matrix = self._reconstruct_vectors(index, vector_ids)
            except (KeyError, RuntimeError, ValueError):
                return self._search_constrained_fallback(
                    index, query, allowed_ids, k, nprobe, ef_search
                )
        if matrix.size == 0:
            return []
        matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        scores = matrix @ query
        order = np.argsort(-scores, kind="stable")[:k]
        return [
            VectorHit(vector_id=vector_ids[int(position)], similarity=float(scores[int(position)]))
            for position in order
        ]

    def score_vectors(
        self,
        index_type: IndexType,
        query_vector: np.ndarray,
        vector_ids: list[int],
        nprobe: int,
        ef_search: int,
        *,
        laptop: bool = False,
    ) -> dict[int, float]:
        """Calculate normalized cosine scores for already-selected vector IDs."""
        return self.score_vectors_multi(
            index_type,
            [query_vector],
            vector_ids,
            nprobe,
            ef_search,
            laptop=laptop,
        )[0]

    def score_vectors_multi(
        self,
        index_type: IndexType,
        query_vectors: list[np.ndarray],
        vector_ids: list[int],
        nprobe: int,
        ef_search: int,
        *,
        laptop: bool = False,
    ) -> list[dict[int, float]]:
        """Score several queries while reconstructing the selected vectors once."""
        if not query_vectors:
            return []
        if not vector_ids:
            return [{} for _ in query_vectors]
        queries = np.ascontiguousarray(
            np.vstack([np.asarray(vector).reshape(-1) for vector in query_vectors]),
            dtype=np.float32,
        )
        if queries.shape[1] != self.settings.embedding_dimension:
            raise ValueError(
                f"Query dimension {queries.shape[1]} does not match configured dimension "
                f"{self.settings.embedding_dimension}."
            )
        queries /= np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
        unique_ids = list(dict.fromkeys(int(value) for value in vector_ids))
        with self._lock:
            index = self._get_index(index_type, laptop=laptop)
            inner = self._inner_index(index)
            if index_type in {IndexType.IVF_FLAT, IndexType.IVF_PQ}:
                inner.nprobe = nprobe
            elif index_type == IndexType.HNSW:
                inner.hnsw.efSearch = ef_search
            try:
                matrix = self._reconstruct_vectors(index, unique_ids)
            except (KeyError, RuntimeError, ValueError):
                matrix = np.empty((0, self.settings.embedding_dimension), dtype=np.float32)
            if matrix.size:
                matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
                all_scores = matrix @ queries.T
                return [
                    {
                        vector_id: float(all_scores[position, query_index])
                        for position, vector_id in enumerate(unique_ids)
                    }
                    for query_index in range(len(query_vectors))
                ]
            raw_results = [
                index.search(query.reshape(1, -1), int(index.ntotal))
                for query in queries
            ]
        allowed = set(unique_ids)
        return [
            {
                int(vector_id): float(np.clip(score, -1.0, 1.0))
                for score, vector_id in zip(raw_scores[0], ids[0])
                if int(vector_id) in allowed
            }
            for raw_scores, ids in raw_results
        ]

    @staticmethod
    def _search_constrained_fallback(
        index,
        query: np.ndarray,
        allowed_ids: list[int],
        k: int,
        nprobe: int,
        ef_search: int,
    ) -> list[VectorHit]:
        """Over-fetch the complete index when old artifacts lack direct maps."""
        inner = FaissIndexManager._inner_index(index)
        if hasattr(inner, "nprobe"):
            inner.nprobe = max(int(nprobe), int(getattr(inner, "nlist", nprobe)))
        if hasattr(inner, "hnsw"):
            inner.hnsw.efSearch = max(int(ef_search), int(index.ntotal))
        scores, ids = index.search(query.reshape(1, -1), int(index.ntotal))
        allowed = {int(value) for value in allowed_ids}
        hits = [
            VectorHit(vector_id=int(vector_id), similarity=float(score))
            for score, vector_id in zip(scores[0], ids[0])
            if int(vector_id) in allowed
        ]
        normalized_scores = FaissIndexManager._normalized_scores(index, query, [hit.vector_id for hit in hits])
        if normalized_scores is not None:
            hits = [
                VectorHit(vector_id=hit.vector_id, similarity=normalized_scores[hit.vector_id])
                for hit in hits
            ]
            hits.sort(key=lambda hit: hit.similarity, reverse=True)
        else:
            hits = [
                VectorHit(vector_id=hit.vector_id, similarity=float(np.clip(hit.similarity, -1.0, 1.0)))
                for hit in hits
            ]
        return hits[:k]

    @staticmethod
    def _normalized_scores(index, query: np.ndarray, vector_ids: list[int]) -> dict[int, float] | None:
        query = np.asarray(query, dtype=np.float32).reshape(-1)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        ids = list(dict.fromkeys(int(value) for value in vector_ids))
        if not ids:
            return {}
        try:
            matrix = FaissIndexManager._reconstruct_vectors(index, ids)
        except (KeyError, RuntimeError, ValueError):
            return None
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 1e-12):
            return None
        matrix /= norms
        scores = matrix @ query
        return {vector_id: float(score) for vector_id, score in zip(ids, scores)}

    @staticmethod
    def _reconstruct_vectors(index, vector_ids: list[int]) -> np.ndarray:
        ids = np.ascontiguousarray(vector_ids, dtype=np.int64)
        if ids.size == 0:
            return np.empty((0, int(index.d)), dtype=np.float32)
        try:
            return np.ascontiguousarray(index.reconstruct_batch(ids), dtype=np.float32)
        except (KeyError, RuntimeError, ValueError):
            vectors = [FaissIndexManager._reconstruct_vector(index, int(value)) for value in ids]
            return np.ascontiguousarray(np.vstack(vectors), dtype=np.float32)

    @staticmethod
    def _reconstruct_vector(index, vector_id: int) -> np.ndarray:
        try:
            return index.reconstruct(int(vector_id))
        except (KeyError, RuntimeError, ValueError):
            if not hasattr(index, "id_map") or not hasattr(index, "index"):
                raise
            mapped_ids = faiss.vector_to_array(index.id_map)
            matches = np.flatnonzero(mapped_ids == int(vector_id))
            if len(matches) == 0:
                raise KeyError(f"Vector ID {vector_id} is not present in the index")
            return index.index.reconstruct(int(matches[0]))

    def search_laptops(
        self,
        index_type: IndexType,
        query_vector: np.ndarray,
        k: int,
        nprobe: int,
        ef_search: int,
    ) -> list[VectorHit]:
        return self.search(
            index_type, query_vector, k, nprobe, ef_search, laptop=True
        )

    def reconstruct_laptop_vector(self, index_type: IndexType, laptop_id: int) -> np.ndarray | None:
        """Fetch a laptop's own stored vector from the laptop-level index, used
        to power 'similar laptops' without any new retrieval logic."""
        with self._lock:
            index = self._get_index(index_type, laptop=True)
            try:
                matrix = self._reconstruct_vectors(index, [int(laptop_id)])
            except (KeyError, RuntimeError, ValueError):
                return None
        return matrix[0] if matrix.size else None

    def search_laptops_constrained(
        self,
        index_type: IndexType,
        query_vector: np.ndarray,
        allowed_laptop_ids: list[int],
        k: int,
        nprobe: int,
        ef_search: int,
    ) -> list[VectorHit]:
        return self.search_constrained(
            index_type,
            query_vector,
            allowed_laptop_ids,
            k,
            nprobe,
            ef_search,
            laptop=True,
        )

    def _get_index(self, index_type: IndexType, *, laptop: bool = False):
        key = index_type.value
        cache_key = f"laptop:{key}" if laptop else key
        if cache_key in self._indexes:
            self._indexes.move_to_end(cache_key)
            return self._indexes[cache_key]
        manifest_indexes = self._manifest.get("laptop_indexes" if laptop else "indexes")
        if manifest_indexes is not None and key not in manifest_indexes:
            kind = "laptop index" if laptop else "index"
            raise FileNotFoundError(f"{kind.title()} {key!r} is not included in the current artifact manifest.")
        filename = (
            manifest_indexes[key]["file"]
            if manifest_indexes is not None
            else f"laptop_{key}.index" if laptop else self.settings.index_files[key]
        )
        path = self.artifacts.ensure(filename)
        index = faiss.read_index(str(path))
        if index.d != self.settings.embedding_dimension:
            raise ValueError(f"Index {key} has dimension {index.d}; expected {self.settings.embedding_dimension}.")
        self._indexes[cache_key] = index
        while len(self._indexes) > self.settings.index_cache_size:
            self._indexes.popitem(last=False)
        return index

    @staticmethod
    def _inner_index(index):
        inner = index.index if hasattr(index, "index") else index
        return faiss.downcast_index(inner)
