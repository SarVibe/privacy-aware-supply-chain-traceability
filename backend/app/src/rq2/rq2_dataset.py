"""Datasets: a reproducible synthetic generator and a CSV loader for real data.

A Dataset is a set of N *unique* entities (raw text + normalized text) with a
probability weight per entity (how often it appears in shipment records). The
weights drive the frequency attack, so real count data is preferable.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.rq2.text_normalizer import normalize


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

    @property
    def n(self) -> int:
        return len(self.raw)


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


def controlled_noise_dataset(
    clean_path: str,
    noise_dir: str,
    noise_level: float,
    seed: int,
    n: int = 1000,
    composite_columns: list[str] | None = None,
) -> Dataset:
    """Load RQ1-generated clean/noisy records and align them by record_id."""
    clean = pd.read_csv(clean_path)
    noise_pct = int(round(noise_level * 100))
    noisy_path = Path(noise_dir) / f"noisy_products_{noise_pct}_seed{seed}.csv"
    if not noisy_path.exists():
        raise FileNotFoundError(
            f"No controlled noise dataset for noise={noise_pct}% and seed={seed}: {noisy_path}"
        )
    noisy = pd.read_csv(noisy_path)

    required_clean = {"record_id", "true_entity_id", "raw_item_description"}
    required_noisy = {"record_id", "raw_item_description"}
    missing_clean = sorted(required_clean - set(clean.columns))
    missing_noisy = sorted(required_noisy - set(noisy.columns))
    if missing_clean:
        raise ValueError(f"Clean master missing required columns: {', '.join(missing_clean)}")
    if missing_noisy:
        raise ValueError(f"Noise dataset missing required columns: {', '.join(missing_noisy)}")
    if len(noisy) != len(clean):
        raise ValueError(
            f"Clean/noisy record count mismatch: clean={len(clean)}, noisy={len(noisy)}"
        )

    merged = clean.merge(
        noisy,
        on="record_id",
        how="inner",
        suffixes=("_clean", "_noisy"),
        validate="one_to_one",
    )
    if len(merged) != len(clean):
        raise ValueError("Clean and noisy datasets do not align by record_id")

    description_col = "raw_item_description_clean"
    noisy_description_col = "raw_item_description_noisy"

    def composed_text(row, noisy: bool = False) -> str:
        if composite_columns:
            parts = [str(row[description_col if not noisy else noisy_description_col] or "")]
            for col in composite_columns:
                clean_col = f"{col}_clean"
                noisy_col = f"{col}_noisy"
                value = row[noisy_col if noisy and noisy_col in row.index else clean_col]
                if pd.notna(value):
                    parts.append(str(value))
            return " ".join(parts)
        return str(row[noisy_description_col if noisy else description_col])

    merged["_clean_text"] = merged.apply(composed_text, axis=1)
    merged["_noisy_text"] = merged.apply(lambda row: composed_text(row, noisy=True), axis=1)
    merged["_clean_norm"] = merged["_clean_text"].map(normalize)
    merged["_noisy_norm"] = merged["_noisy_text"].map(normalize)
    merged = merged[(merged["_clean_norm"] != "") & (merged["_noisy_norm"] != "")]

    entity_col = "true_entity_id_clean"
    groups = merged.groupby(entity_col, sort=False)
    kept = list(groups)
    if len(kept) > n:
        group_rows = []
        for entity_id, group in kept:
            group_rows.append({
                "entity_id": entity_id,
                "raw": group["_clean_text"].astype(str).iloc[0],
                "norm": group["_clean_norm"].astype(str).iloc[0],
                "noisy_norm": group["_noisy_norm"].astype(str).iloc[0],
                "count": len(group),
            })
        sampled = pd.DataFrame(group_rows).sample(
            n=n,
            random_state=seed,
            weights="count",
        ).reset_index(drop=True)
    else:
        group_rows = []
        for entity_id, group in kept:
            group_rows.append({
                "entity_id": entity_id,
                "raw": group["_clean_text"].astype(str).iloc[0],
                "norm": group["_clean_norm"].astype(str).iloc[0],
                "noisy_norm": group["_noisy_norm"].astype(str).iloc[0],
                "count": len(group),
            })
        sampled = pd.DataFrame(group_rows)

    noisy_records = {}
    for position, entity_row in enumerate(sampled.to_dict("records")):
        group = merged[
            merged["true_entity_id_clean"] == entity_row["entity_id"]
        ]
        noisy_records[position] = (
            group["_noisy_norm"].dropna().astype(str).tolist()
        )

    counts = sampled["count"].to_numpy(dtype=float)
    return Dataset(
        raw=sampled["raw"].tolist(),
        norm=sampled["norm"].tolist(),
        weights=counts / counts.sum(),
        source=f"controlled:{clean_path}:{noise_pct}%:seed={seed}",
        counts=counts,
        entity_ids=sampled["entity_id"].tolist(),
        noisy_norm=sampled["noisy_norm"].tolist(),
        noisy_records_by_entity=noisy_records,
        noise_level=noise_level,
        seed=seed,
    )


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
