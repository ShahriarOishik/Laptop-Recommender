import threading
import time
import unittest

import numpy as np

from app.config import Settings
from app.services.embeddings import EmbeddingService


class FakeModel:
    """Stands in for a loaded SentenceTransformer: sleeps to simulate a
    forward pass and logs (thread, start, end) so a test can check whether
    two concurrent encode_many() calls actually overlapped."""

    def __init__(self, delay_seconds: float, log: list[tuple[str, float, float]]):
        self.delay_seconds = delay_seconds
        self.log = log

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False):
        thread_name = threading.current_thread().name
        started = time.monotonic()
        time.sleep(self.delay_seconds)
        ended = time.monotonic()
        self.log.append((thread_name, started, ended))
        return [np.ones(8, dtype=np.float32) for _ in texts]


def _make_service(delay_seconds: float, log: list[tuple[str, float, float]]) -> EmbeddingService:
    service = EmbeddingService(Settings(embedding_dimension=8, cache_max_entries=32))
    service._model = FakeModel(delay_seconds, log)  # bypass .load(), no real model needed
    return service


class EmbeddingServiceCacheTests(unittest.TestCase):
    def test_repeated_text_is_served_from_cache_without_recomputing(self):
        log: list[tuple[str, float, float]] = []
        service = _make_service(delay_seconds=0.0, log=log)

        first = service.encode_many(["a laptop for gaming"])
        second = service.encode_many(["a laptop for gaming"])

        self.assertEqual(len(log), 1)  # only computed once
        np.testing.assert_array_equal(first[0], second[0])

    def test_cache_evicts_oldest_entry_once_over_capacity(self):
        log: list[tuple[str, float, float]] = []
        service = _make_service(delay_seconds=0.0, log=log)
        service._cache_size = 2

        service.encode_many(["one"])
        service.encode_many(["two"])
        service.encode_many(["three"])  # evicts "one"
        service.encode_many(["one"])  # miss again -> recomputed

        self.assertEqual(len(log), 4)


class EmbeddingServiceConcurrencyTests(unittest.TestCase):
    def test_concurrent_encode_many_calls_run_in_parallel_not_serialized(self):
        """Regression test for the lock that used to wrap the entire method,
        including the model forward pass: two concurrent encode_many() calls
        for different (uncached) texts should overlap in their compute
        phase, not queue one-at-a-time behind a single lock."""
        log: list[tuple[str, float, float]] = []
        delay = 0.15
        service = _make_service(delay_seconds=delay, log=log)

        threads = [
            threading.Thread(target=service.encode_many, args=(["gaming laptop text"],), name="t1"),
            threading.Thread(target=service.encode_many, args=(["student laptop text"],), name="t2"),
        ]
        wall_start = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        wall_elapsed = time.monotonic() - wall_start

        self.assertEqual(len(log), 2)
        # If serialized, total wall time would be ~2x the per-call delay.
        # If parallel, it stays close to one delay's worth of time.
        self.assertLess(
            wall_elapsed,
            delay * 1.8,
            f"expected overlapping execution (~{delay}s), took {wall_elapsed:.3f}s — "
            "looks serialized, the lock may be wrapping the model call again",
        )
        (_, start_a, end_a), (_, start_b, end_b) = log
        overlap = min(end_a, end_b) - max(start_a, start_b)
        self.assertGreater(
            overlap,
            0,
            f"expected the two calls' compute windows to overlap, got no overlap: {log}",
        )


if __name__ == "__main__":
    unittest.main()
