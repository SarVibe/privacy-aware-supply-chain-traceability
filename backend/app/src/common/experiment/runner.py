"""Deterministic experiment iteration, row collection, and timing."""

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from itertools import product
from time import perf_counter
from typing import Any

import pandas as pd


def iter_grid(axes: dict[str, list]) -> Iterator[dict[str, Any]]:
    """Yield the Cartesian product in axis and value insertion order."""
    for values in product(*axes.values()):
        yield dict(zip(axes, values, strict=True))


class RunRecorder:
    """Collect rows and construct a DataFrame with a fixed column order."""

    def __init__(self, columns: Sequence[str]) -> None:
        self._columns = tuple(columns)
        self._rows: list[dict[str, Any]] = []

    def add(self, row: Mapping[str, Any]) -> None:
        """Append a row, rejecting keys outside the configured columns."""
        unknown = row.keys() - set(self._columns)
        if unknown:
            raise ValueError(f"Unknown result columns: {', '.join(sorted(unknown))}")
        self._rows.append(dict(row))

    def to_frame(self) -> pd.DataFrame:
        """Return the recorded rows with missing values represented as NaN."""
        return pd.DataFrame.from_records(self._rows, columns=self._columns)


@contextmanager
def timed() -> Iterator[Callable[[], float]]:
    """Yield an elapsed-seconds function whose value freezes on context exit."""
    start = perf_counter()
    end = None

    def elapsed() -> float:
        return (perf_counter() if end is None else end) - start

    try:
        yield elapsed
    finally:
        end = perf_counter()
