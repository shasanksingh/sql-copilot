from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    runtime_root: Path
    cache_root: Path
    sqlite_root: Path
    logs_root: Path
    temp_root: Path
    model_root: Path
    faiss_root: Path
    pip_cache: Path
    npm_cache: Path


def resolve_path(raw: str | None, default: Path, base: Path) -> Path:
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def env_path(name: str, default: Path, base: Path) -> Path:
    return resolve_path(os.getenv(name), default, base)


def load_dotenv_file(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if not name or (name in os.environ and not override):
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[name] = value


def configure_runtime_paths(root_dir: Path) -> RuntimePaths:
    project_root = env_path("SQL_COPILOT_PROJECT_ROOT", root_dir, root_dir)
    runtime_root = env_path("SQL_COPILOT_RUNTIME_DIR", project_root / ".runtime", project_root)
    model_root = env_path(
        "SQL_COPILOT_MODEL_DIR",
        Path(os.getenv("AI_MODELS_DIR", "")) if os.getenv("AI_MODELS_DIR") else runtime_root / "models",
        project_root,
    )
    cache_root = env_path("SQL_COPILOT_CACHE_DIR", runtime_root / "cache", project_root)
    paths = RuntimePaths(
        project_root=project_root,
        runtime_root=runtime_root,
        cache_root=cache_root,
        sqlite_root=env_path("SQL_COPILOT_SQLITE_DIR", runtime_root / "sqlite", project_root),
        logs_root=env_path("SQL_COPILOT_LOG_DIR", runtime_root / "logs", project_root),
        temp_root=env_path("SQL_COPILOT_TEMP_DIR", runtime_root / "tmp", project_root),
        model_root=model_root,
        faiss_root=env_path("SQL_COPILOT_FAISS_DIR", cache_root / "faiss", project_root),
        pip_cache=env_path("PIP_CACHE_DIR", cache_root / "pip", project_root),
        npm_cache=env_path("NPM_CONFIG_CACHE", cache_root / "npm", project_root),
    )

    for path in (
        paths.runtime_root,
        paths.cache_root,
        paths.sqlite_root,
        paths.logs_root,
        paths.temp_root,
        paths.model_root,
        paths.faiss_root,
        paths.pip_cache,
        paths.npm_cache,
    ):
        path.mkdir(parents=True, exist_ok=True)

    environment_defaults = {
        "HF_HOME": paths.model_root / "huggingface",
        "TRANSFORMERS_CACHE": paths.model_root / "huggingface" / "transformers",
        "TORCH_HOME": paths.model_root / "torch",
        "PIP_CACHE_DIR": paths.pip_cache,
        "NPM_CONFIG_CACHE": paths.npm_cache,
        "npm_config_cache": paths.npm_cache,
        "TEMP": paths.temp_root,
        "TMP": paths.temp_root,
        "XDG_CACHE_HOME": paths.cache_root,
    }
    for name, path in environment_defaults.items():
        os.environ.setdefault(name, str(path))

    return paths
