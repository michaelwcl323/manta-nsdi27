"""Dataset layout: each variant keeps geo/lan merge inside its own folder."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# CLI name -> directory under ROOT
DATASET_DIRS: dict[str, str] = {
    "no_coin": "no_flexible_coin",
    "with_coin": "with_coin",
}

DATASET_ALIASES: dict[str, str] = {
    "no_flexible_coin": "no_coin",
}

EXPORT_ENVS: dict[str, tuple[str, ...]] = {
    "no_coin": (
        "geo",
        "geo copy",
        "geo copy 2",
        "new_geo",
        "lan",
        "lan copy",
        "lan copy 2",
    ),
    "with_coin": (
        "geo",
        "geo (2)",
        "geo(3)",
        "geo_FIGA",
        "lan",
        "lan (2)",
        "lan(3)",
        "lanFIGA",
    ),
}

PLOT_ENVS: dict[str, tuple[str, ...]] = {
    "no_coin": ("geo", "geo copy", "new_geo", "lan"),
    "with_coin": (
        "geo",
        "geo (2)",
        "geo(3)",
        "geo_FIGA",
        "lan",
        "lan (2)",
        "lan(3)",
        "lanFIGA",
    ),
}

# Per-dataset merge sources after the primary env (geo / lan).
MERGE_EXTRA: dict[str, dict[str, tuple[str, ...]]] = {
    "no_coin": {
        "geo": ("geo copy 2",),
        "lan": ("lan copy 2",),
    },
    "with_coin": {
        "geo": ("geo (2)", "geo(3)"),
        "lan": ("lan (2)", "lan(3)"),
    },
}

MERGE_PRIMARY = {"geo": "geo", "lan": "lan"}

# Dedicated figure-a sources. When present, fig a does not use the regular merge mix.
FIG_A_ENVS: dict[str, dict[str, tuple[str, ...]]] = {
    "with_coin": {
        "geo": ("geo_FIGA",),
        "lan": ("lanFIGA",),
    },
}

# Fill figure-a keys that the dedicated source is missing (do not mix into present keys).
FIG_A_FILL_ENVS: dict[str, dict[str, tuple[str, ...]]] = {
    "with_coin": {
        "geo": ("lan(3)",),
    },
}

# When averaging a config, keep only the N lowest-latency runs.
KEEP_LOWEST_LATENCY_RUNS = 3


def select_lowest_latency_runs(
    rows: list[dict], keep: int = KEEP_LOWEST_LATENCY_RUNS
) -> list[dict]:
    """Keep up to `keep` runs with the lowest consensus_latency_ms."""
    if len(rows) <= keep:
        return list(rows)
    return sorted(rows, key=lambda r: float(r["consensus_latency_ms"]))[:keep]


def normalize_dataset(name: str) -> str:
    name = DATASET_ALIASES.get(name, name)
    if name not in DATASET_DIRS:
        raise ValueError(f"unknown dataset {name!r}")
    return name


def dataset_path(name: str) -> Path:
    return ROOT / DATASET_DIRS[normalize_dataset(name)]


def _env_has_data(root: Path, env: str) -> bool:
    env_dir = root / env
    if (env_dir / "consensus_summary.csv").exists():
        return True
    return any(
        (env_dir / f"fig_{fig}_runs.csv").exists() for fig in ("a", "b", "c")
    )


def merge_envs(dataset: str, pair: str) -> tuple[str, ...]:
    """Merge sources scoped to one dataset; skip missing optional extras."""
    dataset = normalize_dataset(dataset)
    root = dataset_path(dataset)
    primary = MERGE_PRIMARY[pair]
    envs = [primary]
    for extra in MERGE_EXTRA.get(dataset, {}).get(pair, ()):
        if _env_has_data(root, extra):
            envs.append(extra)
    return tuple(envs)


def fig_a_envs(dataset: str, pair: str) -> tuple[str, ...]:
    """Sources used only for figure a; empty means fall back to merge_envs."""
    dataset = normalize_dataset(dataset)
    root = dataset_path(dataset)
    envs = []
    for env in FIG_A_ENVS.get(dataset, {}).get(pair, ()):
        if _env_has_data(root, env):
            envs.append(env)
    return tuple(envs)


def fig_a_fill_envs(dataset: str, pair: str) -> tuple[str, ...]:
    """Fallback sources for figure-a keys missing from fig_a_envs."""
    dataset = normalize_dataset(dataset)
    root = dataset_path(dataset)
    envs = []
    for env in FIG_A_FILL_ENVS.get(dataset, {}).get(pair, ()):
        if _env_has_data(root, env):
            envs.append(env)
    return tuple(envs)
