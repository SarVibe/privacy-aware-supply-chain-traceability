import pandas as pd
import pytest

from src.common.config import load_config
from src.common.data import loader


def test_raw_reader_preserves_text_fields(tmp_path, monkeypatch):
    path = tmp_path / "shipments.csv"
    path.write_text(
        'item description,dosage,unit of measure (per pack)\n"  Ā!,  ",NA,030\n\nKit,,010\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "raw_csv_path", lambda cfg: path)
    raw = loader.read_raw_csv(load_config("rq1"))
    assert raw.iloc[0].tolist() == ["  Ā!,  ", "NA", "030"]
    assert raw.iloc[1].isna().all()
    assert pd.isna(raw.loc[2, "dosage"])


def test_prepared_and_noisy_readers_preserve_text_and_ids(tmp_path, monkeypatch):
    path = tmp_path / loader.BASE_DATASET_FILENAME
    path.write_text(
        "record_id,entity_id,raw_item_description,dosage,dosage_form,pack_size\n"
        '001,E0001,"  Product!  ",10mg,Tablet,030\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "prepared_dir", lambda cfg: tmp_path)
    cfg = load_config("rq1")
    frame = loader.read_prepared_csv(cfg)
    assert frame.iloc[0].tolist() == ["001", "E0001", "  Product!  ", "10mg", "Tablet", "030"]
    pd.testing.assert_frame_equal(frame, loader.read_noisy_csv(path, cfg))


def test_noise_alignment_uses_record_ids_and_preserves_truth(golden_config):
    cfg = golden_config
    clean = loader.load_noisy(cfg.seeds[0], 0, cfg).head(3)
    noisy = clean.iloc[::-1].assign(raw_item_description=["noise c", "noise b", "noise a"])
    aligned = loader.align_noisy_records(clean, noisy, cfg)
    assert aligned.record_id.tolist() == clean.record_id.tolist()
    assert aligned.raw_item_description.tolist() == ["noise a", "noise b", "noise c"]
    with pytest.raises(ValueError, match="same record IDs"):
        loader.align_noisy_records(clean, noisy.iloc[1:], cfg)
    corrupted_truth = noisy.assign(entity_id="different")
    with pytest.raises(ValueError, match="same entity IDs"):
        loader.align_noisy_records(clean, corrupted_truth, cfg)
