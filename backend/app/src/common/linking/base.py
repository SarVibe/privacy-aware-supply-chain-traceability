"""Shared interface for record linkers."""

from typing import Protocol

from pandas import DataFrame, Series


class Linker(Protocol):
    """Link records without access to their ground-truth entity IDs."""

    name: str

    def link(self, df: DataFrame) -> Series:
        """Return integer cluster labels indexed by record_id for an entity-free frame."""
        ...
