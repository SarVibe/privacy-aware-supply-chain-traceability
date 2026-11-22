import pandas as pd

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
