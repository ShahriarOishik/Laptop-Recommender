import json
import tempfile
import unittest
from pathlib import Path

import faiss
import numpy as np

from app.config import Settings
from app.models import IndexType
from app.services.artifact_store import ArtifactStore
from app.services.faiss_manager import FaissIndexManager


class FaissManagerTests(unittest.TestCase):
    def test_all_saved_id_mapped_indexes_reload_and_search(self):
        rng = np.random.default_rng(42)
        vectors = np.ascontiguousarray(rng.normal(size=(512, 8)), dtype=np.float32)
        faiss.normalize_L2(vectors)
        ids = np.arange(1000, 1512, dtype=np.int64)

        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            bases = {
                "flat": faiss.IndexFlatIP(8),
                "ivf_flat": faiss.IndexIVFFlat(
                    faiss.IndexFlatIP(8), 8, 8, faiss.METRIC_INNER_PRODUCT
                ),
                "pq": faiss.IndexPQ(8, 2, 4, faiss.METRIC_INNER_PRODUCT),
                "ivf_pq": faiss.IndexIVFPQ(
                    faiss.IndexFlatIP(8), 8, 8, 2, 4, faiss.METRIC_INNER_PRODUCT
                ),
                "hnsw": faiss.IndexHNSWFlat(8, 8, faiss.METRIC_INNER_PRODUCT),
            }
            for name, base in bases.items():
                if not base.is_trained:
                    base.train(vectors)
                wrapped = faiss.IndexIDMap2(base)
                wrapped.add_with_ids(vectors, ids)
                faiss.write_index(wrapped, str(artifact_dir / f"{name}.index"))
                faiss.write_index(wrapped, str(artifact_dir / f"laptop_{name}.index"))

            manifest = {
                    "dimension": 8,
                    "vector_count": len(vectors),
                    "indexes": {name: {"file": f"{name}.index"} for name in bases},
                    "laptop_vector_count": len(vectors),
                    "laptop_indexes": {
                        name: {"file": f"laptop_{name}.index"} for name in bases
                    },
            }
            (artifact_dir / "index_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            settings = Settings(
                artifact_dir=artifact_dir,
                embedding_dimension=8,
                index_cache_size=5,
                load_resources_on_startup=False,
            )
            manager = FaissIndexManager(settings, ArtifactStore(artifact_dir))
            for index_type in IndexType:
                hits = manager.search(index_type, vectors[0], 3, nprobe=4, ef_search=32)
                self.assertEqual(len(hits), 3)
                self.assertTrue(all(hit.vector_id in ids for hit in hits))
                constrained = manager.search_constrained(
                    index_type, vectors[0], [int(ids[0])], 3, nprobe=4, ef_search=32
                )
                self.assertEqual([hit.vector_id for hit in constrained], [int(ids[0])])
                self.assertLessEqual(constrained[0].similarity, 1.00001, index_type)
                self.assertGreaterEqual(constrained[0].similarity, -1.00001, index_type)
                laptop_hits = manager.search_laptops(
                    index_type, vectors[0], 3, nprobe=4, ef_search=32
                )
                self.assertEqual(len(laptop_hits), 3)
                laptop_constrained = manager.search_laptops_constrained(
                    index_type, vectors[0], [int(ids[0])], 3, nprobe=4, ef_search=32
                )
                self.assertEqual([hit.vector_id for hit in laptop_constrained], [int(ids[0])])

            scores = manager.score_vectors(
                IndexType.FLAT, vectors[0], [int(ids[0]), int(ids[1])], nprobe=4, ef_search=32
            )
            self.assertAlmostEqual(scores[int(ids[0])], 1.0, places=5)
            multi_scores = manager.score_vectors_multi(
                IndexType.FLAT,
                [vectors[0], vectors[1]],
                [int(ids[0]), int(ids[1])],
                nprobe=4,
                ef_search=32,
            )
            self.assertEqual(len(multi_scores), 2)
            self.assertAlmostEqual(multi_scores[0][int(ids[0])], 1.0, places=5)
            self.assertAlmostEqual(multi_scores[1][int(ids[1])], 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
