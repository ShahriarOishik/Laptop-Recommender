from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

import httpx


class ArtifactStore:
    def __init__(self, artifact_dir: Path, base_url: str | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.base_url = base_url.rstrip("/") if base_url else None
        self._lock = Lock()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def ensure(self, filename: str) -> Path:
        path = self.artifact_dir / filename
        if path.exists():
            return path
        if not self.base_url:
            raise FileNotFoundError(
                f"Artifact {filename!r} was not found in {self.artifact_dir}. "
                "Set ARTIFACT_BASE_URL to download artifacts at runtime."
            )
        with self._lock:
            if path.exists():
                return path
            temporary = path.with_suffix(path.suffix + ".part")
            url = f"{self.base_url}/{filename}"
            try:
                with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return path
