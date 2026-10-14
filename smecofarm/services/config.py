"""Chargement de config.yaml et des secrets du fichier .env."""

import os
from pathlib import Path

import yaml  # pip install pyyaml (ou sudo apt install python3-yaml)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_env(path):
    """Lit un fichier .env simple (CLE=valeur) et le place dans os.environ.

    Les variables déjà définies dans l'environnement sont prioritaires.
    """
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path=None, env_path=None):
    path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    load_env(env_path or PROJECT_ROOT / ".env")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def secret(name):
    """Valeur d'un secret (.env ou variable d'environnement), None si absente."""
    value = os.environ.get(name, "").strip()
    return value or None
