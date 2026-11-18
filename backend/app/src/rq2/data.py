"""Datasets: a reproducible synthetic generator and a CSV loader for real data.

A Dataset is a set of N *unique* entities (raw text + normalized text) with a
probability weight per entity (how often it appears in shipment records). The
weights drive the frequency attack, so real count data is preferable.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .preprocess import normalize


@dataclass
class Dataset:
    raw: list
    norm: list
    weights: np.ndarray   # probabilities, sum to 1
    source: str

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
    return Dataset(raw, [normalize(r) for r in raw], _zipf_weights(n, rng), f"synthetic(n={n},seed={seed})")


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
    )


def load_dataset(data: str | None, column: str | None, n: int, seed: int = 0,
                 composite_columns: list[str] | None = None) -> Dataset:
    if data:
        return csv_dataset(data, column, n, seed, composite_columns)
    return synthetic_dataset(n, seed)
