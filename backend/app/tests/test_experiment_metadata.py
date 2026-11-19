import sys
from pathlib import Path

import pandas as pd

from src.common.experiment_metadata import add_common_args, write_markdown


def test_markdown_fallback(tmp_path, monkeypatch):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    def raise_import_error(*args, **kwargs):
        raise ImportError("tabulate unavailable")

    monkeypatch.setattr(pd.DataFrame, "to_markdown", raise_import_error)
    path = tmp_path / "table.md"
    write_markdown(df, path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("| a | b |")
    assert "| --- | --- |" in text
    assert "| 1 | x |" in text


def test_markdown_to_markdown_when_available(tmp_path, monkeypatch):
    df = pd.DataFrame({"a": [1], "b": ["x"]})
    called = {"value": False}

    def fake_to_markdown(self, **kwargs):
        called["value"] = True
        return "| a | b |\n| --- | --- |\n| 1 | x |"

    monkeypatch.setattr(pd.DataFrame, "to_markdown", fake_to_markdown)
    path = tmp_path / "table.md"
    write_markdown(df, path)
    assert called["value"]
    assert "| 1 | x |" in path.read_text(encoding="utf-8")
