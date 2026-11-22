# RQ1 reproducibility command guide

Run these PowerShell blocks from the checkout's `backend/` directory, in one session. Start a new session or repeat setup to create a new run directory for each attempt. Paths beginning with `app/` are relative to `backend/`. The original `app/results/rq1`, `rq1_posthoc`, `rq1_legacy`, and `rq1_audit` are read-only references throughout.

**VERIFIED** means the invocation was executed for this guide, with output shown. **HELP-ONLY** means only the indicated help invocation ran. **NOT RUN** means the recipe was checked against source or CLI syntax, with the reason given. The full ten-seed run, P1/P2 and audit replay recipes are separate from the seed-0 checks performed for this guide.

## 1. Setup

**VERIFIED · Direct interpreter and scratch environment.** If you are at the repository root, enter `backend/` first. The checked environment matches `RQ1_AUDIT.md:9`. For tests and read-only checks, use `PYTHONPATH=app`. For scratch experiment commands, Section 3 replaces it with the absolute path of the copied app.

```powershell
$ErrorActionPreference = 'Stop'
$py = '.\venv313\Scripts\python.exe'
$run = Join-Path (Get-Location).Path ('app/results/rq1_repro/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $run -Force | Out-Null
$env:PYTHONPATH = 'app'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MPLCONFIGDIR = Join-Path $run 'mplconfig'
$env:TEMP = $run
$env:TMP = $run
& $py -V
& $py -B -c "import sys; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix)"
& $py -B -m pip --version
```

Trimmed output:

```text
Python 3.13.17
…\backend\venv313\Scripts\python.exe
venv: True
pip 26.3 from …\backend\venv313\Lib\site-packages\pip (python 3.13)
```

**VERIFIED · Activation attempt, exit blocked by PowerShell policy.** Activation is optional. Calling `$py` directly uses the intended interpreter without a policy change.

```powershell
& .\venv313\Scripts\Activate.ps1
```

```text
Activate.ps1 cannot be loaded because running scripts is disabled on this system.
```

**HELP-ONLY · Optional dependency installation flags.** This help succeeded and listed `--target`, `--no-compile`, `--no-cache-dir`, and `--disable-pip-version-check`.

```powershell
& $py -B -m pip install --help
```

**NOT RUN · Install requirements only if packages are missing.** The existing venv passed the checks, so no packages were installed. This recipe writes to `$run\packages` and leaves the venv untouched. The requirements declare version ranges. An installation performed later may select different versions and yield a mismatch.

```powershell
$packages = Join-Path $run 'packages'
& $py -B -m pip install --ignore-installed --target $packages --no-compile --no-cache-dir --disable-pip-version-check -r .\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$env:PYTHONPATH = "app;$packages"
```

If you used the optional package directory, append `;$packages` whenever a later command assigns `PYTHONPATH`.

**Files:** New scratch directory and temporary caches, plus `packages/` only if installed. **Time:** A few seconds for setup. Download/install time is unmeasured and depends on network and package availability. **Worked if:** The interpreter path ends in `backend\venv313\Scripts\python.exe` and the check returns `venv: True`.

## 2. Quick sanity · full tests

**VERIFIED ·** Run before switching to the copied app. `$run/pytest` is fresh. Pytest can clear a pre-existing `--basetemp`, so use a new `$run` for each test attempt.

```powershell
& $py -B -m pytest -p no:cacheprovider --basetemp (Join-Path $run 'pytest') --tb=short | Tee-Object -FilePath (Join-Path $run 'pytest.log')
if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
```

```text
platform win32 -- Python 3.13.17, pytest-8.4.2
collected 233 items
233 passed in 53.53s
```

**Files:** `$run/pytest.log`, temporary fixtures and the scratch Matplotlib cache. **Time:** About 54 seconds. **Worked if:** Pytest exits zero and all collected tests pass.

## 3. Prepare the data in a copied app

**VERIFIED ·** The preparation CLI has only `--stage {base,split,noise}`. Its output paths are resolved from the imported app's `src/common/paths.py`, so selecting the copied app is what puts every preparation output under scratch. The source dataset filename really is `Suppy_Chain_Shipment_Data.csv`. [Preparation CLI](../backend/app/experiments/rq1/prepare_rq1_data.py#L91) · [Path resolver](../backend/app/src/common/paths.py#L10) · [Configuration](../backend/app/configs/base.yaml#L1)

```powershell
$scratchApp = Join-Path $run 'app'
New-Item -ItemType Directory -Path $scratchApp,(Join-Path $scratchApp 'experiments'),(Join-Path $scratchApp 'data') | Out-Null
Copy-Item -LiteralPath app/src,app/configs -Destination $scratchApp -Recurse
Copy-Item -LiteralPath app/experiments/rq1,app/experiments/__init__.py -Destination (Join-Path $scratchApp 'experiments') -Recurse
Copy-Item -LiteralPath app/data/raw -Destination (Join-Path $scratchApp 'data') -Recurse
$env:PYTHONPATH = $scratchApp
foreach ($stage in @('base','split','noise')) {
    & $py -B -m experiments.rq1.prepare_rq1_data --stage $stage | Tee-Object -FilePath (Join-Path $run "prepare-$stage.log")
    if ($LASTEXITCODE -ne 0) { throw "Preparation failed at $stage" }
}
```

```text
Base: 1,855 rows, 149 entities from 10,324 raw rows
Rows removed: 8,469 (0 empty description or empty row, 8,469 from 68 capped entities, 0 from entity sampling).
Splitting 1,855 rows from 149 entities.
Seed 0: validation 45 entities / 545 rows, test 104 entities / 1,310 rows
Seed 9: validation 45 entities / 518 rows, test 104 entities / 1,337 rows
Seed  Level  Selected records  Actual rate
0     5%                   93       5.013%
0     15%                 278      14.987%
0     30%                 556      29.973%
```

**Files:** Under `$scratchApp/data/generated`, `prepared/base_dataset.csv`, `prepared/entity_map.csv`, ten `splits/split_seed*.json`, and 30 noisy CSVs plus 30 edit logs under `noisy/seed0` through `seed9`. The 0% baseline loads `base_dataset.csv` directly. The stage logs live under `$run`. **Time:** About 7 seconds in total. **Worked if:** There are 1,855 records in 149 groups, 45/104 validation/test groups in every split, and 93/278/556 selected records per seed at 5/15/30%. [Noise loading](../backend/app/src/common/data/loader.py#L55)

## 4. Run the experiment

Run with `PYTHONPATH` still pointing at `$scratchApp`. The defaults use seeds 0–9, noise levels 0/5/15/30%, description and composite, both SHA-256 exact methods, and pure Bloom fuzzy with single and per-noise cutoffs. The runner tunes on validation entities and scores test entities. [Configuration](../backend/app/configs/rq1.yaml) · [Execution order](../backend/app/experiments/rq1/run_rq1.py#L156)

**NOT RUN · Full frozen-design replication.** The seed-0 execution below covers the same path. The full execution was outside the verification run requested for this guide. The option is defined at `run_rq1.py:233`.

```powershell
$full = Join-Path $run 'full'
& $py -B -m experiments.rq1.run_rq1 --out-dir $full
if ($LASTEXITCODE -ne 0) { throw 'Full run failed' }
```

**VERIFIED · Seed 0 with an explicit scratch output.** This runs every noise level and both field sets.

```powershell
$seed0 = Join-Path $run 'seed0'
& $py -B -m experiments.rq1.run_rq1 --seeds 0 --out-dir $seed0
if ($LASTEXITCODE -ne 0) { throw 'Seed 0 failed' }
```

```text
RQ1 results written to …\app\results\rq1_repro\20261122-205559-a30b06ae\seed0
```

**NOT RUN · Smoke flag or two-seed quick check.** The explicit seed-0 run was used for verification. `--smoke` accepts seed 0 only and the code pins its destination to the active app's `results/rq1/smoke`. Run it only with the scratch `PYTHONPATH`. The separate two-seed command uses `--seeds 0 1` without `--smoke`. [Smoke destination and options](../backend/app/experiments/rq1/run_rq1.py#L46) · [Seed restriction](../backend/app/experiments/rq1/run_rq1.py#L117)

```powershell
$env:PYTHONPATH = $scratchApp
& $py -B -m experiments.rq1.run_rq1 --smoke
if ($LASTEXITCODE -ne 0) { throw 'Smoke run failed' }
$quick = Join-Path $run 'quick-0-1'
& $py -B -m experiments.rq1.run_rq1 --seeds 0 1 --out-dir $quick
if ($LASTEXITCODE -ne 0) { throw 'Two-seed run failed' }
```

**VERIFIED · Help attempt failed.** The flag definitions were checked in `run_rq1.py:226–247`. The literal `5%` in the noise option's help text triggers argparse's percent formatting error. The execution commands above use those definitions directly.

```powershell
& $py -B -m experiments.rq1.run_rq1 --help
```

```text
ValueError: incomplete format
```

**Files:** Each destination contains `raw_runs.csv`, `tau_selection.csv`, and `metadata.json`. **Time:** Seed 0 took 12.6 seconds. Expect roughly 20–30 seconds for two seeds and around 1½–2 minutes for ten seeds, based on historical and measured runtimes. **Worked if:** There are 32 test and 320 tuning rows per seed, giving 320 and 3,200 for the full run. [Historical timing](RQ1_RESULTS.md#how-to-reproduce)

## 5. Build the report

**VERIFIED · Seed-0 report.** Run with the scratch app on `PYTHONPATH`.

```powershell
$report0 = Join-Path $run 'report-seed0'
& $py -B -m experiments.rq1.build_rq1_report --input (Join-Path $seed0 'raw_runs.csv') --tau-input (Join-Path $seed0 'tau_selection.csv') --out-dir $report0
if ($LASTEXITCODE -ne 0) { throw 'Seed-0 report failed' }
```

```text
RQ1 report written to …\rq1_repro\20261122-205559-a30b06ae\report-seed0
- At 5% typos, did Fuzzy match (Bloom filter) reach an F1 score of at least 0.90? **no** (0.8993).
```

**NOT RUN · Full report variant.** The full ten-seed inputs were not regenerated for this guide. Report options were verified on the seed-0 invocation. [Report CLI](../backend/app/experiments/rq1/build_rq1_report.py#L286)

```powershell
$report = Join-Path $run 'report'
& $py -B -m experiments.rq1.build_rq1_report --input (Join-Path $full 'raw_runs.csv') --tau-input (Join-Path $full 'tau_selection.csv') --out-dir $report
if ($LASTEXITCODE -ne 0) { throw 'Full report failed' }
```

**Files:** `tables/table1_f1_by_noise`, `table2_fragmentation_precision`, `table3_ablation_field_set`, `table4_tau_sensitivity`, and `table5_paired_difference`, each with `.csv`, `.md`, `.tex`. Also `figures/fig1_f1_vs_noise.png`, `figures/fig2_fragmentation_vs_noise.png`, and `h1_check.md`. **Time:** About 5 seconds for seed 0. **Worked if:** Both figures and the H1 note exist and the tables use the intended seed scope.

## 6. Validate the complete result

**VERIFIED · Read-only validation of the frozen complete run.** This exercises the production validator without rewriting results. Keep `PYTHONPATH` as it was in Section 5 until after the full report if you still intend to build it.

```powershell
$env:PYTHONPATH = 'app'
$frozen = (Resolve-Path app/results/rq1).Path
& $py -B -m experiments.rq1.validate_rq1_results --input (Join-Path $frozen 'raw_runs.csv') --tau-input (Join-Path $frozen 'tau_selection.csv') | Tee-Object -FilePath (Join-Path $run 'validator.log')
if ($LASTEXITCODE -ne 0) { throw 'Frozen validation failed' }
```

```text
PASS: Raw grid has exactly 320 rows and the required combinations (found 320)
PASS: Validation tuning covers exactly 3200 grid rows (found 3200)
PASS: Test cutoffs match the validation-only selections
PASS: Single-tau boundary choices: 0/20 (0.0%)
WARN: F1 sample SD exceeds 0.05 in 16 groups (maximum 0.1832)
```

**NOT RUN · Validate the new full-run files.** This path variant requires the unrun ten-seed replay. The CLI accepts the same two input flags. Use the comparator in Section 9 for a seed-0 check because the validator expects all configured seeds and the original method grid. [Validator checks and exit codes](../backend/app/experiments/rq1/validate_rq1_results.py#L59)

```powershell
& $py -B -m experiments.rq1.validate_rq1_results --input (Join-Path $full 'raw_runs.csv') --tau-input (Join-Path $full 'tau_selection.csv')
if ($LASTEXITCODE -ne 0) { throw 'Fresh full validation failed' }
```

**Files:** `$run/validator.log` for the verified invocation. **Time:** A few seconds. **Worked if:** Exit code is 0 with 14 passing checks, one variability warning and zero failures on the reproduced design. The warning means fuzzy F1 varied across seeds in groups whose sample SD exceeded 0.05. It does not cause a nonzero exit.

## 7. POST-HOC P1 and P2

**VERIFIED · Verify scratch preparation against saved input hashes.** This check establishes that P1 receives the saved 30/70 split bytes and that both runs receive the same prepared and noisy data.

```powershell
$count = 0
foreach ($dir in @('prepared','splits','noisy')) {
    $saved = (Resolve-Path (Join-Path 'app/data/generated' $dir)).Path
    $fresh = (Resolve-Path (Join-Path "$scratchApp/data/generated" $dir)).Path
    foreach ($file in Get-ChildItem -LiteralPath $saved -Recurse -File) {
        $copy = Join-Path $fresh ($file.FullName.Substring($saved.Length + 1))
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $copy).Hash) {
            throw "Prepared input differs: $copy"
        }
        $count++
    }
}
"Prepared input hashes match: $count files"
```

```text
Prepared input hashes match: 72 files
```

**NOT RUN · POST-HOC evaluations and reports.** Long runs were outside the verification requested for this guide. `--post-hoc`, `--val-fraction`, and `--out-dir` were verified against `run_rq1.py:128–148,229–247` because its help crashes. Both evaluation and reporting enforce a destination within the **active app's** `results/rq1_posthoc/`. Pointing `PYTHONPATH` at the scratch app satisfies that constraint without writing into the original checkout result tree. The report detects blocked rows from the input. [Post-hoc path guard](../backend/app/experiments/rq1/posthoc.py#L25) · [Report routing](../backend/app/experiments/rq1/build_rq1_report.py#L214)

```powershell
$env:PYTHONPATH = $scratchApp
$p1 = Join-Path $scratchApp 'results/rq1_posthoc/p1_blocked_split3070'
$p2 = Join-Path $scratchApp 'results/rq1_posthoc/p2_split5050'
& $py -B -m experiments.rq1.run_rq1 --post-hoc p1 --val-fraction 0.30 --out-dir $p1
if ($LASTEXITCODE -ne 0) { throw 'P1 failed' }
& $py -B -m experiments.rq1.run_rq1 --post-hoc p2 --val-fraction 0.50 --out-dir $p2
if ($LASTEXITCODE -ne 0) { throw 'P2 failed' }
foreach ($dest in @($p1,$p2)) {
    & $py -B -m experiments.rq1.build_rq1_report --input (Join-Path $dest 'raw_runs.csv') --tau-input (Join-Path $dest 'tau_selection.csv') --out-dir $dest
    if ($LASTEXITCODE -ne 0) { throw "Post-hoc report failed: $dest" }
}
```

**Files:** Each analysis has run and tuning CSVs, `metadata.json`, Tables 1, 2, and 5 in three formats, and two PNGs. P2 also saves ten new `splits/split_seed*.json`. There is no primary H1 note in the post-hoc reports. **Time:** Historically about 2¼ minutes per analysis plus a few seconds for the report. **Worked if:** Each run has 360 test and 4,800 tuning rows, blocked rows are present, and report titles say “Post-hoc analysis.” [Phase 7b outputs and timing](ARCHITECTURE.md#phase-7b-complete--post-hoc-analyses-p1-and-p2)

## 8. Re-run the independent audit

**NOT RUN · New scratch audit snapshot and all five scripts.** This long replay was outside the verification scope. The scripts do not expose a help parser, so adding `--help` would execute their work. Their paths derive from each script's location. Copy them into `audit_workspace/backend/app/results/audit_outputs` to keep all writes separate. Copy the reference data and reports that the scripts expect at adjacent paths. `check_claims.py` reads the copied `RQ1_RESULTS.md` using fixed line ranges, so preserve that file's text.

```powershell
$auditRoot = Join-Path $run 'audit_workspace'
$auditApp = Join-Path $auditRoot 'backend/app'
$auditOutput = Join-Path $auditApp 'results/audit_outputs'
New-Item -ItemType Directory -Path $auditOutput,(Join-Path $auditApp 'data/generated'),(Join-Path $auditRoot 'docs') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $scratchApp 'src'),(Join-Path $scratchApp 'experiments'),(Join-Path $scratchApp 'configs') -Destination $auditApp -Recurse
Copy-Item -LiteralPath app/data/raw -Destination (Join-Path $auditApp 'data') -Recurse
Copy-Item -LiteralPath app/data/generated/prepared,app/data/generated/splits,app/data/generated/noisy -Destination (Join-Path $auditApp 'data/generated') -Recurse
Copy-Item -LiteralPath app/results/rq1,app/results/rq1_posthoc -Destination (Join-Path $auditApp 'results') -Recurse
Copy-Item -LiteralPath ../docs/RQ1_RESULTS.md -Destination (Join-Path $auditRoot 'docs')
$scripts = @('check_artifacts.py','independent_metrics.py','check_statistics.py','check_claims.py','replay_seed0.py')
foreach ($script in $scripts) {
    Copy-Item -LiteralPath (Join-Path 'app/results/rq1_audit' $script) -Destination $auditOutput
}
$env:PYTHONPATH = $auditApp
foreach ($script in $scripts) {
    $log = Join-Path $auditOutput ([IO.Path]::ChangeExtension($script,'log'))
    & $py -B -u (Join-Path $auditOutput $script) | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Audit script failed: $script" }
}
$env:PYTHONPATH = 'app'
```

| Script                   | Expected files under `audit_outputs/` and success check                                                                                                     | Approximate runtime                    |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `check_artifacts.py`     | `noise_verification.csv`, `clean_lookalikes.csv`, and log. All 30 noisy files pass checks and the clean profile has 26 pairs. Run before `check_claims.py`. | Several seconds                        |
| `independent_metrics.py` | `metric_recomputation.csv` and log. 18 comparisons, maximum difference near 1.11e-16.                                                                       | Several to tens of seconds             |
| `check_statistics.py`    | `paired_statistics.csv`, `descriptive_scores.csv`, `field_set_ablation.csv`, and log. Six published paired rows match in each of frozen/P1/P2.              | A few seconds                          |
| `check_claims.py`        | `numeric_token_changes.csv` and log. Reads `clean_lookalikes.csv`, checks 33 embedded score rows and ten clean-profile examples.                            | A few seconds                          |
| `replay_seed0.py`        | `rerun/scratch_app`, `rerun/outputs`, and log. 32 test and 320 tuning rows match with runtime ignored.                                                      | About 11 seconds in the original audit |

**Worked if:** All five exit zero and the output matches the checks above. Timings are approximate and derive from the original audit commands, not the scratch copy recipe. [Audit evidence and previous replay](RQ1_AUDIT.md#evidence-and-commands)

## 9. Compare fresh and frozen scores

**VERIFIED · Seed-0 exact comparison.** Save this comparator under the current scratch directory. It reads both CSVs with round-trip float parsing, retains row and column order, and ignores `runtime_sec` in raw rows only. Omit `--seeds` for a full comparison.

```powershell
@'
"""Compare a fresh RQ1 run with a read-only frozen reference."""
import argparse
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fresh", type=Path)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+")
    args = parser.parse_args()
    try:
        for filename in ("raw_runs.csv", "tau_selection.csv"):
            actual, expected = (
                pd.read_csv(directory / filename, float_precision="round_trip")
                for directory in (args.fresh, args.frozen)
            )
            if args.seeds is not None:
                expected = expected[expected["seed"].isin(args.seeds)].reset_index(drop=True)
            if filename == "raw_runs.csv":
                actual = actual.drop(columns="runtime_sec")
                expected = expected.drop(columns="runtime_sec")
            pd.testing.assert_frame_equal(actual, expected, check_exact=True)
            print(f"MATCH {filename}: {len(actual)} rows")
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        print(f"MISMATCH {filename}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -Encoding ASCII (Join-Path $run 'compare_rq1.py')
$frozen = (Resolve-Path app/results/rq1).Path
& $py -B (Join-Path $run 'compare_rq1.py') $seed0 $frozen --seeds 0 | Tee-Object -FilePath (Join-Path $run 'compare-seed0.log')
if ($LASTEXITCODE -ne 0) { throw 'Seed-0 comparison failed' }
```

```text
MATCH raw_runs.csv: 32 rows
MATCH tau_selection.csv: 320 rows
```

**NOT RUN · Full comparison invocation.** Requires the unrun full evaluation in Section 4. The same comparator and reference were executed for seed 0.

```powershell
& $py -B (Join-Path $run 'compare_rq1.py') $full $frozen
if ($LASTEXITCODE -ne 0) { throw 'Full comparison failed' }
```

**Files:** `$run/compare_rq1.py` and `$run/compare-seed0.log`. **Time:** A few seconds. **Worked if:** It prints two `MATCH` lines with the expected row counts and exits zero. A `MISMATCH` reports the first file and error and exits 1.

## 10. Where to find the final numbers

**VERIFIED · Read-only file and header inspection.** The main numbers below come from the frozen ten-seed run. In `raw_runs.csv`, filter `split=test`, `field_set=composite`, and the `noise_level` of interest (`0.05`, `0.15`, `0.30`). For fuzzy select `method=bloom_fuzzy`, `tau_mode=single`. For exact select `method=raw_exact` or `normalized_exact`, `tau_mode=none`. Take the mean across seeds. `tau_selection.csv` contains validation scores, so it is only a source for cutoff selection.

```powershell
Get-Content -TotalCount 2 app/results/rq1/raw_runs.csv,app/results/rq1/tau_selection.csv,app/results/rq1/tables/table5_paired_difference.csv,app/results/rq1_audit/field_set_ablation.csv
```

| Headline result                            | Exact frozen or audit file and column                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mean F1 at 5/15/30%                        | `app/results/rq1/tables/table1_f1_by_noise.csv`, columns `5%`, `15%`, `30%` and row `Method`. Cleaned exact .909/.811/.649, pure fuzzy .786/.770/.757. Unrounded source `raw_runs.csv`, column `f1`.                                                                                                                                                                                                    |
| Precision                                  | `app/results/rq1/tables/table2_fragmentation_precision.csv`, `Precision (share of linked pairs that are correct)`. Unrounded source `raw_runs.csv`, `precision`.                                                                                                                                                                                                                                        |
| Recall                                     | `app/results/rq1/raw_runs.csv`, `recall`. The fuzzy-only field-set summary is `tables/table3_ablation_field_set.csv`, `Recall (share of true pairs found)`.                                                                                                                                                                                                                                             |
| Fragmentation                              | `app/results/rq1/tables/table2_fragmentation_precision.csv`, `Average separate groups per product (1.0 = perfect)`. Unrounded source `raw_runs.csv`, `fragmentation_rate`. A value of 1.0 measures no splitting and can coexist with incorrect merges.                                                                                                                                                  |
| Holm-adjusted primary p-values at 5/15/30% | `app/results/rq1/tables/table5_paired_difference.csv`, `Holm-adjusted one-sided p-value`, fuzzy minus cleaned exact rows. Values 1.0000/1.0000/.0293. Use `app/results/rq1_audit/paired_statistics.csv`, `p_greater_holm`, for more digits, filtered to `run=frozen`, `baseline=normalized_exact`.                                                                                                      |
| Field-set ablation                         | `app/results/rq1/tables/table3_ablation_field_set.csv`, `Fields used`, `Share of records with typos`, `F1 score (higher is better)`, `Precision (share of linked pairs that are correct)`, `Recall (share of true pairs found)`. The audit's exploratory all-method comparison is `app/results/rq1_audit/field_set_ablation.csv`, `description_*`, `composite_*`, `p_greater_holm`, `p_two_sided_holm`. |

**Files written:** None. **Time:** Seconds. **Worked if:** The CSV headers match the table and the 30% result remains the sole positive-noise result below 0.05 in the prespecified comparison.

## 11. Troubleshooting

| Symptom                   | Fix and check                                                                                                                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wrong working directory   | Check `Get-Location` and use `backend/`, which contains `venv313`, `app`, and `requirements.txt`. The interpreter and the relative PowerShell paths then resolve.                                                                                                                   |
| Missing `PYTHONPATH`      | Use `$env:PYTHONPATH = 'app'` for checkout reads and the test suite. For preparation/evaluation/reporting use `$env:PYTHONPATH = $scratchApp`. `experiments.rq1` is the import path.                                                                                                |
| Protected destination     | For ordinary runs use `--out-dir $full` or `$seed0` and send the report to scratch as well. `--smoke` derives its destination from the imported app. Post-hoc output must be below that app's `results/rq1_posthoc/`. [Guard](../backend/app/experiments/rq1/posthoc.py#L17)        |
| Missing data file         | Check that the scratch copy includes `data/raw/Suppy_Chain_Shipment_Data.csv`. If the missing file is generated, rerun Section 3 in a fresh scratch app in `base`, `split`, `noise` order.                                                                                          |
| Missing or wrong HMAC key | Copy the original YAMLs again. The configured `bloom.hmac_key` in `base.yaml` must be valid hex and match the frozen fingerprint. The runner decodes it from config. Use the check below to avoid printing key material. [Key load](../backend/app/src/common/linking/bloom.py#L37) |

**VERIFIED · Read-only raw input and key fingerprint check.** The verification used the checkout's `PYTHONPATH='app'`. To diagnose the scratch copy, use `$scratchApp` as the first `PYTHONPATH` entry before running this block.

```powershell
@'
from hashlib import sha256
import json
from pathlib import Path
from src.common.config import load_config
from src.common.paths import raw_csv_path
cfg = load_config('rq1')
key = bytes.fromhex(cfg.bloom.hmac_key)
assert key, 'Empty research key'
fingerprint = sha256(key).hexdigest()[:12]
saved = json.loads(Path('app/results/rq1/metadata.json').read_text(encoding='utf-8'))
print('HMAC key fingerprint matches frozen metadata:', fingerprint == saved['config']['bloom']['hmac_key_fingerprint'])
print('Raw input is present:', raw_csv_path(cfg).is_file())
'@ | & $py -B -
```

```text
HMAC key fingerprint matches frozen metadata: True
Raw input is present: True
```

**Files written:** None. **Time:** Seconds. **Worked if:** The expected path is shown by `Get-Location` and the two checks return `True`.

### Corrections needed in the older recipe

- `docs/RQ1_RESULTS.md:17,44,57,61` describes or passes `app/results/rq1/` as the output destination. The current guard rejects it once the final raw, tuning, metadata, and H1 files exist. Use the copied app and the explicit scratch destinations in this guide for preparation, evaluation and reporting. The read-only validator invocation at line 69 remains valid. [Old recipe](RQ1_RESULTS.md#how-to-reproduce) · [Current guard](../backend/app/experiments/rq1/posthoc.py#L17)
- `run_rq1.py:230–232` contains the unescaped percent sign in `--noise-levels` help. The observed failure affects help rendering. The verified `--seeds 0 --out-dir` invocation parsed and ran successfully. [Runner parser](../backend/app/experiments/rq1/run_rq1.py#L226)

### Other CLI help evidence

**HELP-ONLY** for these specific invocations. They printed the documented options and exited zero. The actual execution statuses are recorded in their sections.

```powershell
& $py -B -m experiments.rq1.prepare_rq1_data --help
& $py -B -m experiments.rq1.build_rq1_report --help
& $py -B -m experiments.rq1.validate_rq1_results --help
```

```text
prepare_rq1_data.py [-h] --stage {base,split,noise}
build_rq1_report.py [-h] [--input INPUT] [--tau-input TAU_INPUT] [--out-dir OUT_DIR]
validate_rq1_results.py [-h] [--input INPUT] [--tau-input TAU_INPUT]
```

Verification artifacts from this guide are under `app/results/rq1_repro/20261122-205559-a30b06ae/`.
