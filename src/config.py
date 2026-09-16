"""One configuration surface for the CLI, API, and dashboard."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, repr=False)
class Settings:
    backend: str = "sqlite"
    database_path: Path = ROOT / "data/processed/products.db"
    model_path: Path = ROOT / "artifacts/category/model.json"
    report_dir: Path = ROOT / "artifacts/category"
    api_key: str = ""
    ollama_url: str = ""
    ollama_model: str = ""

    @classmethod
    def from_env(cls):
        env = {**dotenv_values(ROOT / ".env"), **os.environ}
        backend = env.get("PLATFORM_BACKEND", env.get("DASHBOARD_BACKEND", "sqlite"))
        if backend not in ("sqlite", "postgres"):
            raise ValueError("PLATFORM_BACKEND must be sqlite or postgres.")
        model = Path(env.get("MODEL_PATH", str(ROOT / "artifacts/category/model.json")))
        return cls(
            backend,
            Path(env.get("SQLITE_PATH", str(ROOT / "data/processed/products.db"))),
            model,
            model.parent,
            env.get("PLATFORM_API_KEY", ""),
            env.get("OLLAMA_URL", ""),
            env.get("OLLAMA_MODEL", ""),
        )
