import pandas as pd
import pytest

from src.common.config import load_config
from src.common.data.schema import required_columns, validate_frame


def test_validates_record_table_shape_and_identity():
    cfg = load_config("rq1")
    columns = required_columns(cfg)
    frame = pd.DataFrame([("r1", "E0001", "Alpha", "", "Capsule", "30")], columns=columns)
    validate_frame(frame, cfg)
    with pytest.raises(ValueError, match="missing required columns: dosage_form"):
        validate_frame(frame.drop(columns="dosage_form"), cfg)
    with pytest.raises(ValueError, match="non-null and unique"):
        validate_frame(pd.concat([frame, frame]), cfg)
    with pytest.raises(ValueError, match="entity_id must be non-null"):
        validate_frame(frame.assign(entity_id=None), cfg)
