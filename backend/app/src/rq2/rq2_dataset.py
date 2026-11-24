"""Datasets: a reproducible synthetic generator and a CSV loader for real data.

A Dataset is a set of N *unique* entities (raw text + normalized text) with a
probability weight per entity (how often it appears in shipment records). The
weights drive the frequency attack, so real count data is preferable.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import Config
from src.common.data.loader import LinkageData, load_linkage_data
from src.common.preprocessing.field_builder import build_field_strings
from src.common.preprocessing.normalizer import normalize


@dataclass
class Dataset:
    raw: list
    norm: list
    weights: np.ndarray   # probabilities, sum to 1
    source: str
    counts: np.ndarray | None = None
    entity_ids: list | None = None
    noisy_norm: list | None = None
    noise_level: float | None = None
    seed: int | None = None
    frequency_weights: np.ndarray | None = None
    frequency_counts: np.ndarray | None = None
    noisy_records_by_entity: dict[int, list[str]] | None = None
    linkage: LinkageData | None = None

    @property
    def n(self) -> int:
        return len(self.raw)


def load_research_dataset(
    cfg: Config, seed: int, noise: float, *, field_set: str = "composite", max_records: int | None = None
) -> Dataset:
    """Load RQ1's paired records and derive the RQ2 entity-level privacy population."""
    linkage = load_linkage_data(cfg, seed, noise, field_set, max_records=max_records)
    return privacy_dataset(linkage, seed, noise)


def privacy_dataset(linkage: LinkageData, seed: int, noise: float) -> Dataset:
    """Build entity representatives and variant frequencies from the paired records."""
    cfg, clean, noisy, field_set = linkage.config, linkage.clean, linkage.noisy, linkage.field_set
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    observations = clean[[rid, eid]].set_index(rid).assign(
        clear=build_field_strings(clean, field_set, cfg, normalize=False),
        normalized=build_field_strings(clean, field_set, cfg, normalize=True),
        observed=build_field_strings(noisy, field_set, cfg, normalize=True),
    )
    groups = list(observations.groupby(eid, sort=False))
    counts = np.array([len(group) for _, group in groups])
    return Dataset(
        raw=[group["clear"].iloc[0] for _, group in groups],
        norm=[group["normalized"].iloc[0] for _, group in groups],
        weights=counts / counts.sum(),
        source=f"prepared:seed={seed}:noise={noise:g}",
        counts=counts,
        entity_ids=[entity for entity, _ in groups],
        noisy_norm=[group["observed"].iloc[0] for _, group in groups],
        noisy_records_by_entity={index: group["observed"].tolist() for index, (_, group) in enumerate(groups)},
        noise_level=noise,
        seed=seed,
        linkage=linkage,
    )


_DRUGS = ["Lamivudine", "Zidovudine", "Nevirapine", "Efavirenz", "Tenofovir Disoproxil Fumarate",
          "Abacavir", "Lopinavir/Ritonavir", "Atazanavir", "Dolutegravir", "Stavudine", "Didanosine",
          "Emtricitabine", "Raltegravir", "Darunavir", "Rilpivirine", "Isoniazid", "Rifampicin",
          "Pyrazinamide", "Ethambutol", "Paracetamol", "Amoxicillin", "Cotrimoxazole", "Fluconazole",
          "Artemether/Lumefantrine"]
_DOSES = ["10mg", "25mg", "50mg", "100mg", "150mg", "200mg", "300mg", "600mg"]
_FORMS = ["Tablets", "Capsules", "Oral Solution", "Dispersible Tablets", "Injection"]
_PACKS = ["30 Tabs", "60 Tabs", "100 Tabs", "240ml Bottle", "Blister Pack of 10", "Bottle of 60"]


def _zipf_weights(n: int, rng: np.random.Generator, s: float = 1.0) -> np.ndarray:
    w = 1.0 / np.arange(1, n + 1) ** s
    rng.shuffle(w)
    return w / w.sum()


def synthetic_dataset(n: int = 1000, seed: int = 0) -> Dataset:
    rng = np.random.default_rng(seed)
    combos = [f"{d} {dose}, {f}, {p}" for d in _DRUGS for dose in _DOSES for f in _FORMS for p in _PACKS]
    if n > len(combos):
        raise ValueError(f"synthetic generator supports at most {len(combos)} entities")
    pick = rng.choice(len(combos), size=n, replace=False)
    raw = [combos[i] for i in pick]
    weights = _zipf_weights(n, rng)
    return Dataset(
        raw,
        [normalize(r) for r in raw],
        weights,
        f"synthetic(n={n},seed={seed})",
        counts=np.maximum(np.rint(weights * 10000), 1),
        entity_ids=list(range(n)),
    )


def resolve_columns(df: pd.DataFrame, column: str | None,
                    composite_columns: list[str] | None = None) -> tuple[str, list[str]]:
    """Resolve RQ1-style names and real-CSV aliases to actual column names."""
    aliases = {
        "raw_item_description": ["raw_item_description", "item description"],
        "dosage": ["dosage"],
        "dosage_form": ["dosage_form", "dosage form"],
        "pack_size": ["pack_size", "unit of measure (per pack)"],
    }

    def resolve(name: str) -> str:
        for candidate in aliases.get(name, [name]):
            if candidate in df.columns:
                return candidate
        raise ValueError(
            f"Required column '{name}' not found in {list(df.columns)}"
        )

    primary = resolve(column) if column else resolve("raw_item_description")
    if composite_columns:
        extra = [resolve(name) for name in composite_columns]
    else:
        extra = []
    return primary, extra


def csv_dataset(path: str, column: str | None, n: int = 1000, seed: int = 0,
                composite_columns: list[str] | None = None) -> Dataset:
    """Unique normalized values, optionally combining composite attributes."""
    df = pd.read_csv(path)
    primary, extra = resolve_columns(df, column, composite_columns)
    df = df[[primary, *extra]].dropna(how="all")

    if extra:
        df["_text"] = df[primary].fillna("").astype(str)
        for attribute in extra:
            df["_text"] = df["_text"] + " " + df[attribute].fillna("").astype(str)
        source_column = "_text"
    else:
        source_column = primary

    df["_norm"] = df[source_column].map(normalize)
    df = df[df["_norm"] != ""]
    grp = df.groupby("_norm").agg(raw=(source_column, "first"), count=(source_column, "size")).reset_index()
    if len(grp) > n:
        grp = grp.sample(n=n, random_state=seed, weights="count").reset_index(drop=True)
    w = grp["count"].to_numpy(dtype=float)
    representation = "composite" if extra else "description"
    return Dataset(
        grp["raw"].astype(str).tolist(),
        grp["_norm"].tolist(),
        w / w.sum(),
        f"csv:{path}:{primary}:{representation}",
        counts=w,
        entity_ids=list(range(len(grp))),
    )


def load_dataset(data: str | None, column: str | None, n: int, seed: int = 0,
                 composite_columns: list[str] | None = None) -> Dataset:
    if data:
        return csv_dataset(data, column, n, seed, composite_columns)
    return synthetic_dataset(n, seed)


def apply_real_frequency_counts(
    ds: Dataset,
    raw_path: str,
    seed: int = 0,
) -> Dataset:
    """Apply raw shipment-row counts by normalized description, with a floor of one."""
    frequency_ds = csv_dataset(
        raw_path,
        "raw_item_description",
        n=max(ds.n, 1000),
        seed=seed,
    )
    count_by_norm = {
        norm: count
        for norm, count in zip(frequency_ds.norm, frequency_ds.counts)
    }
    counts = np.array(
        [float(count_by_norm.get(norm, 1.0)) for norm in ds.norm],
        dtype=float,
    )
    ds.counts = counts
    ds.frequency_counts = counts.copy()
    ds.frequency_weights = counts / counts.sum()
    ds.weights = ds.frequency_weights.copy()
    ds.source = f"{ds.source}:frequency={raw_path}"
    return ds
