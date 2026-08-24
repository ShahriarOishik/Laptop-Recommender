from __future__ import annotations

from collections import OrderedDict
from threading import Lock

import numpy as np

from app.config import Settings


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = Lock()
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_size = max(settings.cache_max_entries * 4, 256)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from sentence_transformers import SentenceTransformer

            kwargs = {"device": self.settings.embedding_device} if self.settings.embedding_device else {}
            model = SentenceTransformer(self.settings.embedding_model, **kwargs)
            model.max_seq_length = 512
            # sentence-transformers renamed this accessor; the project
            # supports >=3.3,<6 so both names are tried rather than pinning
            # to whichever happens to be installed locally.
            get_dimension = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
            dimension = get_dimension()
            if dimension != self.settings.embedding_dimension:
                raise ValueError(
                    f"Embedding model dimension {dimension} does not match configured dimension "
                    f"{self.settings.embedding_dimension}."
                )
            self._model = model

    def encode(self, text: str) -> np.ndarray:
        return self.encode_many([text])[0]

    def encode_many(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        self.load()
        results: list[np.ndarray | None] = [None] * len(texts)
        missing: list[str] = []
        missing_positions: dict[str, list[int]] = {}
        with self._lock:
            for position, text in enumerate(texts):
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    results[position] = cached.copy()
                else:
                    if text not in missing_positions:
                        missing.append(text)
                        missing_positions[text] = []
                    missing_positions[text].append(position)

        # The actual model forward pass runs *outside* the lock so that
        # concurrent calls (each on its own asyncio.to_thread worker) can
        # genuinely run in parallel instead of queuing one-at-a-time behind
        # a single process-wide lock. This is safe because SentenceTransformer
        # .encode() only reads model parameters under torch.no_grad() — no
        # shared mutable state is written during inference, unlike the cache
        # dict below, which is why that part still needs the lock. The
        # tradeoff: if the same uncached text is requested by two concurrent
        # calls before either finishes, both recompute it once rather than
        # one waiting on the other — occasional duplicate work, never
        # incorrect results, and far cheaper than serializing every request.
        if missing:
            vectors = self._model.encode(
                missing,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            with self._lock:
                for text, vector in zip(missing, vectors):
                    contiguous = np.ascontiguousarray(vector, dtype=np.float32)
                    self._cache[text] = contiguous
                    self._cache.move_to_end(text)
                    for position in missing_positions[text]:
                        results[position] = contiguous.copy()
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return [vector for vector in results if vector is not None]
