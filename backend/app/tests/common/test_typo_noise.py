import pandas as pd
import pytest

from src.common.data import loader
from src.common.noise.typo_noise import apply_typo, inject_noise
from src.common.seeding import make_rng

_DESCRIPTION = "raw_item_description"


def _distance(a: str, b: str) -> int:
    """Compute Damerau-Levenshtein distance, including adjacent swaps."""
    limit = len(a) + len(b)
    table = [[0] * (len(b) + 2) for _ in range(len(a) + 2)]
    table[0][0] = limit
    for i in range(len(a) + 1):
        table[i + 1][0], table[i + 1][1] = limit, i
    for j in range(len(b) + 1):
        table[0][j + 1], table[1][j + 1] = limit, j
    last_row = {}
    for i, left in enumerate(a, 1):
        last_match = 0
        for j, right in enumerate(b, 1):
            i_prev, j_prev = last_row.get(right, 0), last_match
            cost = int(left != right)
            if cost == 0:
                last_match = j
            table[i + 1][j + 1] = min(
                table[i][j] + cost,
                table[i + 1][j] + 1,
                table[i][j + 1] + 1,
                table[i_prev][j_prev] + i - i_prev - 1 + 1 + j - j_prev - 1,
            )
        last_row[left] = i
    return table[-1][-1]


def _digits(text: str) -> str:
    return "".join(char for char in text if char.isdigit())


def _records(n: int = 137) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_id": [f"R{i:04d}" for i in range(n)],
            "entity_id": [f"E{i // 2:04d}" for i in range(n)],
            _DESCRIPTION: [f"Alpha {i} 60/30mg [trial], 2.5 ml, ٣ tablets" for i in range(n)],
            "dosage": ["60/30mg"] * n,
            "dosage_form": ["Coated tablet"] * n,
            "pack_size": ["030"] * n,
        },
        index=[i // 2 for i in range(n)],
    )


@pytest.mark.parametrize("kind", ["substitute", "delete", "insert", "transpose"])
def test_apply_typo_edits_once_without_touching_digits(kind):
    original = "alpha 60/30+20mg, 2.5 ml"
    mutated = apply_typo(original, make_rng(4, "single_typo"), kind)
    assert _distance(original, mutated) == 1
    assert _digits(mutated) == _digits(original)
    assert "60/30+20" in mutated and "2.5" in mutated
    assert len(mutated) - len(original) == {"insert": 1, "delete": -1}.get(kind, 0)


def test_apply_typo_cannot_swap_equal_characters():
    assert apply_typo("aa3", make_rng(0, "swap"), "transpose") == "aa3"


@pytest.mark.parametrize("level", [0.05, 0.15, 0.30])
def test_exact_record_selection_and_protected_fields(level):
    df = _records()
    noisy, log = inject_noise(df, level, [_DESCRIPTION], (1, 2), make_rng(3, f"noise_{level}"))
    changed = noisy[_DESCRIPTION].ne(df[_DESCRIPTION])
    assert changed.sum() == round(level * len(df))
    assert set(log["record_id"]) == set(df.loc[changed, "record_id"])
    assert len(log) == log["record_id"].nunique() and log["skipped_reason"].eq("").all()
    pd.testing.assert_frame_equal(noisy.loc[~changed], df.loc[~changed])
    pd.testing.assert_frame_equal(noisy.drop(columns=_DESCRIPTION), df.drop(columns=_DESCRIPTION))
    for row in log.itertuples(index=False):
        assert _digits(row.original) == _digits(row.mutated)
        assert 1 <= _distance(row.original, row.mutated) <= row.n_typos <= 2
        assert len(row.typo_kinds.split("|")) == row.n_typos


def test_two_edits_cannot_cancel_or_strand_a_short_value():
    df = _records(30).assign(raw_item_description="1a2")
    noisy, log = inject_noise(df, 1, [_DESCRIPTION], (2, 2), make_rng(7, "two_typos"))
    assert noisy[_DESCRIPTION].ne(df[_DESCRIPTION]).all()
    assert log["n_typos"].eq(2).all()
    assert log["mutated"].map(_digits).eq("12").all()


def test_seed_replays_noise_and_controls_record_selection():
    df = _records()

    def run(seed):
        return inject_noise(df, 0.15, [_DESCRIPTION], (1, 2), make_rng(seed, "noise_0.15"))

    first_frame, first_log = run(0)
    replay_frame, replay_log = run(0)
    other_frame, other_log = run(1)
    pd.testing.assert_frame_equal(first_frame, replay_frame)
    pd.testing.assert_frame_equal(first_log, replay_log)
    assert set(first_log["record_id"]) != set(other_log["record_id"])
    assert not first_frame.equals(other_frame)
    assert df[_DESCRIPTION].str.startswith("Alpha").all()


def test_zero_returns_input_unchanged_with_an_empty_log():
    df = _records()
    noisy, log = inject_noise(df, 0.0, [_DESCRIPTION], (1, 2), make_rng(0, "noise_0.0"))
    pd.testing.assert_frame_equal(df, noisy)
    assert log.empty
    assert log.columns.tolist() == [
        "record_id", "field", "n_typos", "typo_kinds", "original", "mutated", "skipped_reason"
    ]


def test_short_numeric_and_missing_values_are_logged_as_skips():
    df = _records(5)
    df[_DESCRIPTION] = ["ab", "123４", "60/30", None, "abc"]
    noisy, log = inject_noise(df, 1.0, [_DESCRIPTION], (1, 2), make_rng(0, "skip"))
    by_id = log.set_index("record_id").loc[df["record_id"]]
    assert by_id["skipped_reason"].tolist() == [
        "short_text", "no_valid_typo", "no_valid_typo", "missing_text", ""
    ]
    assert (by_id["n_typos"].iloc[:4] == 0).all()
    pd.testing.assert_frame_equal(noisy.iloc[:4], df.iloc[:4])
    assert noisy[_DESCRIPTION].iloc[4] != "abc"


def test_two_noise_fields_preserve_other_columns_and_share_record_edit_budget():
    df = _records()
    fields = [_DESCRIPTION, "dosage_form"]
    noisy, log = inject_noise(df, 0.30, fields, (1, 2), make_rng(0, "noise_0.3"))
    changed_description = noisy[_DESCRIPTION].ne(df[_DESCRIPTION])
    changed_form = noisy["dosage_form"].ne(df["dosage_form"])
    pd.testing.assert_series_equal(changed_description, changed_form, check_names=False)
    pd.testing.assert_frame_equal(noisy.drop(columns=fields), df.drop(columns=fields))
    assert log.groupby("record_id")["n_typos"].nunique().eq(1).all()
    assert log.groupby("record_id")["field"].nunique().eq(2).all()
    assert log["record_id"].nunique() == round(0.30 * len(df))
    assert all(1 <= _distance(row.original, row.mutated) <= 2 for row in log.itertuples())


def test_configured_identity_columns_cannot_be_mutated():
    df = _records(2).rename(columns={"record_id": "rid", "entity_id": "ground_truth"})
    rng = make_rng(0, "noise_1.0")
    with pytest.raises(ValueError, match="ID columns"):
        inject_noise(
            df, 1.0, ["ground_truth"], (1, 2), rng,
            record_id_column="rid", entity_id_column="ground_truth",
        )


def test_load_noisy_zero_returns_the_base_frame(monkeypatch, tmp_path):
    base = _records(2)
    base.to_csv(tmp_path / loader.BASE_DATASET_FILENAME, index=False)
    monkeypatch.setattr(loader, "prepared_dir", lambda cfg: tmp_path)
    loaded = loader.load_noisy(99, 0.0)
    pd.testing.assert_frame_equal(loaded, base.reset_index(drop=True))


def test_load_noisy_resolves_seed_and_percent(monkeypatch, tmp_path):
    base = _records(2)
    (tmp_path / "seed3").mkdir()
    base.to_csv(tmp_path / "seed3" / "noise_05.csv", index=False)
    monkeypatch.setattr(loader, "noisy_dir", lambda cfg: tmp_path)
    pd.testing.assert_frame_equal(loader.load_noisy(3, 0.05), base.reset_index(drop=True))
