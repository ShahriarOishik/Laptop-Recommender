import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from app.config import Settings
from app.container import ServiceContainer
from app.services.hybrid_metadata_store import HybridQdrantMetadataStore


class ContainerCatalogMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.temporary.name)
        pd.DataFrame(
            [
                {"vector_id": 1, "laptop_id": 10},
                {"vector_id": 2, "laptop_id": 20},
            ]
        ).to_parquet(self.artifact_dir / "laptop_metadata.parquet", index=False)

    def tearDown(self):
        self.temporary.cleanup()

    def _container(self, laptop_count: int) -> ServiceContainer:
        (self.artifact_dir / "index_manifest.json").write_text(
            json.dumps({"vector_count": 9, "laptop_vector_count": laptop_count}),
            encoding="utf-8",
        )
        settings = replace(
            Settings(),
            artifact_dir=self.artifact_dir,
            metadata_backend="qdrant",
            qdrant_url="https://qdrant.example.test",
            load_resources_on_startup=False,
        )
        return ServiceContainer(settings)

    def test_qdrant_initialization_ensures_and_validates_laptop_sidecar(self):
        container = self._container(laptop_count=2)
        original_ensure = container.artifacts.ensure
        container.artifacts.ensure = Mock(wraps=original_ensure)

        with patch("app.container.QdrantMetadataStore") as qdrant_type:
            qdrant_type.return_value.health.return_value = True
            container.initialize()

        container.artifacts.ensure.assert_called_once_with("laptop_metadata.parquet")
        qdrant_type.return_value.health.assert_called_once_with(768, 9)
        self.assertTrue(container.metadata_ready)
        self.assertIsInstance(container.metadata, HybridQdrantMetadataStore)

    def test_qdrant_initialization_rejects_sidecar_count_mismatch(self):
        container = self._container(laptop_count=3)

        with patch("app.container.QdrantMetadataStore"):
            container.initialize()

        self.assertFalse(container.metadata_ready)
        self.assertIsNone(container.metadata)
        self.assertTrue(any("expected 3" in error for error in container.startup_errors))


if __name__ == "__main__":
    unittest.main()
