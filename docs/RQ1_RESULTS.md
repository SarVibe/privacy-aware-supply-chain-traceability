# RQ1 results

## What was tested

- The study asked how well three methods link different shipment records about the same product when descriptions contain typos.
- The original shipment file had 10,324 records. The prepared dataset kept 1,855 records across 149 product groups, with at most 20 records per group.
- A product group was defined by molecule or test type, dosage, dosage form, and pack size.
- The four conditions were 0% (clean control), 5%, 15%, and 30% of records selected for one or two typos. Typos affected the description field.
- Each of the ten seeds, 0–9, assigned whole product groups to validation or test in an approximately 30/70 split.
- The comparators were exact matching on original text, exact matching on cleaned text, and fuzzy matching using a keyed Bloom filter and Dice similarity.
- The primary comparison used description, dosage, form, and pack size. Description alone was a second comparison.
- For each seed and field set, the main fuzzy cutoff maximized average validation F1 over the four typo levels. The sensitivity analysis selected one cutoff per level.
- Only pairs within the held-out test split contributed to reported performance. F1 summarizes precision and recall. Fragmentation counts how many predicted groups contain each repeated product, averaged across repeated products.

## How to reproduce

Run the following in PowerShell from `backend/` with the project’s Python 3.13 environment. The preparation stages write to a scratch copy, and the runner and report builder write to `app/results/rq1/`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$rq7Test = Join-Path ([IO.Path]::GetTempPath()) ('rq1-p7-pytest-' + [guid]::NewGuid().ToString('N'))
$env:MPLCONFIGDIR = Join-Path ([IO.Path]::GetTempPath()) ('rq1-p7-test-mpl-' + [guid]::NewGuid().ToString('N'))
.\venv313\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $rq7Test --tb=short
```

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='app'
$env:MPLCONFIGDIR = Join-Path ([IO.Path]::GetTempPath()) ('rq1-p7-report-mpl-' + [guid]::NewGuid().ToString('N'))
@'
import sys
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from experiments.rq1 import prepare_rq1_data, run_rq1
from experiments.rq1.build_rq1_report import build_report
from src.common import paths
from src.common.config import load_config

cfg = load_config("rq1")
source, out = paths.raw_csv_path(cfg), paths.results_dir(cfg, "rq1")
started = perf_counter()
with TemporaryDirectory(prefix="rq1-p7-full-") as directory:
    scratch = Path(directory).resolve()
    with patch.object(paths, "app_dir", return_value=scratch):
        scratch_raw = paths.raw_csv_path(cfg)
        scratch_raw.parent.mkdir(parents=True)
        copyfile(source, scratch_raw)
        for stage in ("base", "split", "noise"):
            with patch.object(sys, "argv", ["prepare_rq1_data", "--stage", stage]):
                prepare_rq1_data.main()
        print(f"PREP_SECONDS={perf_counter()-started:.3f}", flush=True)
        t = perf_counter()
        run_rq1.main(["--out-dir", str(out)])
        print(f"EXPERIMENT_SECONDS={perf_counter()-t:.3f}", flush=True)

t = perf_counter()
build_report(out / "raw_runs.csv", out / "tau_selection.csv", out)
print(f"REPORT_SECONDS={perf_counter()-t:.3f}", flush=True)
print(f"FULL_SECONDS={perf_counter()-started:.3f}", flush=True)
'@ | .\venv313\Scripts\python.exe -u -B -
```

```powershell
$env:PYTHONPATH='app'
.\venv313\Scripts\python.exe -B -m experiments.rq1.validate_rq1_results --input app/results/rq1/raw_runs.csv --tau-input app/results/rq1/tau_selection.csv
```

The pre-run suite passed 218 tests and the final suite passed 228. The full preparation, evaluation, and reporting workflow took **99.693 seconds**. Evaluation alone took 93.255 seconds. The validator reported 14 passes, one warning and zero failures. F1 sample standard deviation exceeded 0.05 in 16 groups, with a maximum of 0.1832. There were zero single-threshold boundary selections out of 20, and mean F1 for each exact method declined as noise increased.

The seed 0 replay started again from the raw CSV in a separate temporary directory. It regenerated the base, split and noisy files, then ran the existing runner with `--seeds 0`. All 32 seed 0 result rows matched exactly after excluding the measured runtime column, and all 320 validation tuning rows matched. The redacted configuration snapshot and HMAC key fingerprint matched. The replay took 10.876 seconds.

## Results

Scores come from the held-out test splits. Except where labeled otherwise, the tables average across ten seeds and show the sample standard deviation after `+-`.

### Table 1. F1 by share of records with typos

**F1 score (higher is better) by share of records with typos**

| Method                      | 0% (control)   | 5%             | 15%            | 30%            | F1 score drop (0% to 30%) |
| --------------------------- | -------------- | -------------- | -------------- | -------------- | ------------------------- |
| Exact match (original text) | 0.958 +- 0.008 | 0.905 +- 0.012 | 0.800 +- 0.011 | 0.621 +- 0.015 | 0.337                     |
| Exact match (cleaned text)  | 0.958 +- 0.008 | 0.909 +- 0.011 | 0.811 +- 0.014 | 0.649 +- 0.014 | 0.309                     |
| Fuzzy match (Bloom filter)  | 0.792 +- 0.140 | 0.786 +- 0.134 | 0.770 +- 0.121 | 0.757 +- 0.108 | 0.035                     |

F1 balances how often predicted links are correct with how many true links the method finds.

### Table 2. Separate groups and precision

| Method                      | Share of records with typos | Average separate groups per product (1.0 = perfect) | Precision (share of linked pairs that are correct) |
| --------------------------- | --------------------------- | --------------------------------------------------- | -------------------------------------------------- |
| Exact match (original text) | 0% (control)                | 1.206 +- 0.026                                      | 1.000 +- 0.000                                     |
| Exact match (original text) | 5%                          | 1.927 +- 0.084                                      | 1.000 +- 0.000                                     |
| Exact match (original text) | 15%                         | 3.288 +- 0.082                                      | 1.000 +- 0.000                                     |
| Exact match (original text) | 30%                         | 5.407 +- 0.138                                      | 1.000 +- 0.000                                     |
| Exact match (cleaned text)  | 0% (control)                | 1.206 +- 0.026                                      | 1.000 +- 0.000                                     |
| Exact match (cleaned text)  | 5%                          | 1.870 +- 0.087                                      | 1.000 +- 0.000                                     |
| Exact match (cleaned text)  | 15%                         | 3.137 +- 0.105                                      | 1.000 +- 0.000                                     |
| Exact match (cleaned text)  | 30%                         | 5.076 +- 0.144                                      | 1.000 +- 0.000                                     |
| Fuzzy match (Bloom filter)  | 0% (control)                | 1.098 +- 0.067                                      | 0.704 +- 0.215                                     |
| Fuzzy match (Bloom filter)  | 5%                          | 1.186 +- 0.161                                      | 0.704 +- 0.215                                     |
| Fuzzy match (Bloom filter)  | 15%                         | 1.361 +- 0.389                                      | 0.697 +- 0.213                                     |
| Fuzzy match (Bloom filter)  | 30%                         | 1.612 +- 0.698                                      | 0.702 +- 0.214                                     |

F1 balances how often predicted links are correct with how many true links the method finds.

### Table 3. Description alone versus four fields

| Fields used                           | Share of records with typos | F1 score (higher is better) | Precision (share of linked pairs that are correct) | Recall (share of true pairs found) |
| ------------------------------------- | --------------------------- | --------------------------- | -------------------------------------------------- | ---------------------------------- |
| Description only                      | 0% (control)                | 0.758 +- 0.183              | 0.672 +- 0.241                                     | 0.948 +- 0.029                     |
| Description only                      | 5%                          | 0.750 +- 0.177              | 0.672 +- 0.241                                     | 0.931 +- 0.042                     |
| Description only                      | 15%                         | 0.732 +- 0.163              | 0.669 +- 0.240                                     | 0.898 +- 0.080                     |
| Description only                      | 30%                         | 0.711 +- 0.152              | 0.670 +- 0.240                                     | 0.855 +- 0.114                     |
| Description + dosage, form, pack size | 0% (control)                | 0.792 +- 0.140              | 0.704 +- 0.215                                     | 0.958 +- 0.030                     |
| Description + dosage, form, pack size | 5%                          | 0.786 +- 0.134              | 0.704 +- 0.215                                     | 0.946 +- 0.041                     |
| Description + dosage, form, pack size | 15%                         | 0.770 +- 0.121              | 0.697 +- 0.213                                     | 0.925 +- 0.069                     |
| Description + dosage, form, pack size | 30%                         | 0.757 +- 0.108              | 0.702 +- 0.214                                     | 0.894 +- 0.105                     |

F1 balances how often predicted links are correct with how many true links the method finds.

### Table 4. One cutoff versus a cutoff for each typo level

| Share of records with typos | F1 score (higher is better), one cutoff | F1 score (higher is better), cutoff per typo level | Average cutoff across typo levels | Average cutoff at this typo level |
| --------------------------- | --------------------------------------- | -------------------------------------------------- | --------------------------------- | --------------------------------- |
| 0% (control)                | 0.792 +- 0.140                          | 0.876 +- 0.143                                     | 0.918                             | 0.949                             |
| 5%                          | 0.786 +- 0.134                          | 0.831 +- 0.126                                     | 0.918                             | 0.935                             |
| 15%                         | 0.770 +- 0.121                          | 0.771 +- 0.121                                     | 0.918                             | 0.916                             |
| 30%                         | 0.757 +- 0.108                          | 0.752 +- 0.100                                     | 0.918                             | 0.910                             |

F1 balances how often predicted links are correct with how many true links the method finds.

### Table 5. Paired F1 differences

| Share of records with typos | Comparison                                                   | Mean F1 score difference | Sample standard deviation | 95% interval for the mean difference | Wins / seeds | Holm-adjusted one-sided p-value |
| --------------------------- | ------------------------------------------------------------ | ------------------------ | ------------------------- | ------------------------------------ | ------------ | ------------------------------- |
| 5%                          | Fuzzy match (Bloom filter) minus Exact match (cleaned text)  | -0.124                   | 0.134                     | [-0.220, -0.028]                     | 2/10         | 1.0000                          |
| 15%                         | Fuzzy match (Bloom filter) minus Exact match (cleaned text)  | -0.042                   | 0.123                     | [-0.130, 0.047]                      | 5/10         | 1.0000                          |
| 30%                         | Fuzzy match (Bloom filter) minus Exact match (cleaned text)  | 0.107                    | 0.106                     | [0.031, 0.183]                       | 8/10         | 0.0293                          |
| 5%                          | Fuzzy match (Bloom filter) minus Exact match (original text) | -0.120                   | 0.134                     | [-0.215, -0.024]                     | 2/10         | –                               |
| 15%                         | Fuzzy match (Bloom filter) minus Exact match (original text) | -0.030                   | 0.123                     | [-0.118, 0.058]                      | 5/10         | –                               |
| 30%                         | Fuzzy match (Bloom filter) minus Exact match (original text) | 0.136                    | 0.107                     | [0.059, 0.212]                       | 9/10         | –                               |

F1 balances how often predicted links are correct with how many true links the method finds.

[Figure 1. F1 score versus share of records with typos](../backend/app/results/rq1/figures/fig1_f1_vs_noise.png)

[Figure 2. Average separate groups per product versus share of records with typos](../backend/app/results/rq1/figures/fig2_fragmentation_vs_noise.png)

## Observed outcome for H1

The comparisons below use the main composite field set and single fuzzy cutoff. The planned adjusted p-value cutoff for the comparison with cleaned-text exact matching was 0.05. The original-text exact comparison is descriptive.

- **5% typos:** In these experiments, fuzzy F1 was **0.7856**, below **0.9094** for cleaned-text exact matching and **0.9052** for original-text exact matching. It also fell below the planned 0.90 target. It beat the cleaned-text baseline in 2 of 10 seeds, and the adjusted p-value was 1.0000. The 5% H1 outcome did not meet either criterion.
- **15% typos:** Fuzzy F1 was **0.7697**, below **0.8113** for cleaned-text exact matching and **0.7995** for original-text exact matching. It beat the cleaned-text baseline in 5 of 10 seeds, and the adjusted p-value was 1.0000. The 15% H1 outcome did not meet the criterion.
- **30% typos:** Fuzzy F1 was **0.7565**, above **0.6491** for cleaned-text exact matching and **0.6206** for original-text exact matching. It beat the cleaned-text baseline in 8 of 10 seeds, with a mean paired advantage of 0.107 and an adjusted p-value of 0.0293. The 30% H1 outcome met the planned criterion in these experiments.

## Ablation and tau-sensitivity findings

On the held-out splits, fuzzy matching with all four fields had higher mean F1 than description alone at every typo level. The gap ranged from about 0.034 in the clean control to 0.046 at 30% typos. Selecting a separate cutoff per level raised composite fuzzy F1 from 0.792 to 0.876 in the control and from 0.786 to 0.831 at 5%. The sensitivity result was nearly unchanged at 15% and slightly lower at 30%. The primary comparisons above use the prespecified single cutoff.

## Limitations

- The typos were synthetic, and the study used one dataset. Other sources may contain different kinds of errors.
- The definition of a product group is a modelling choice. Two alternatives such as different brands can share a group if the four defining fields agree.
- Typos were applied to the description only. Dosage, form, and pack size contributed text to the composite match, with no separate rule that required those fields to agree before matching.
- About **9%** of selected noisy records in seed 0’s held-out test split (58 of 639, **9.1%**) changed only in spaces or punctuation that normalization removes. Across all 9,270 selections in the full dataset and ten seeds, this stricter count was **686 (7.4%)**. A total of 693 selections (7.5%) produced identical normalized descriptions.
- The exact baseline’s mean F1 was already 0.9094 at 5% noise, leaving little room for improvement at that level.
- Reported performance uses pairs formed inside the test split only. Grouping by connected components can chain together records through intermediate matches, even when two end records would score below the cutoff on their own.
- Fuzzy F1 varied materially across seeds. The composite single-cutoff sample standard deviation ranged from 0.108 to 0.140 across the four levels.

### Descriptive profile of similar clean records

This profile used all 1,855 prepared records. A pair of distinct product groups counted if any clean record from one group had a Bloom-filter Dice score of at least 0.92 against any clean record from the other, using normalized composite fields. Each group pair is listed once and ranked by its highest record-pair score. The last column compares the letters and digits in the two raw descriptions shown. The profile was computed after the experiment and did not inform cutoff selection.

There were **26** such product-group pairs. Across the ten seeds, an average of **15.8** fell in the same split, with **1.8** in validation and **14.0** in test. These counts describe where similar records occur in the dataset.

| Product groups | First raw description                                                   | Second raw description                                                            | Highest Dice | Difference   |
| -------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------- | -----------: | ------------ |
| E0006 / E0008  | Abacavir/Lamivudine 60/30mg, tablets, 30 Tabs                           | Abacavir/Lamivudine 600/300mg, tablets, 30 Tabs                                   |       0.9876 | digits only  |
| E0006 / E0007  | Abacavir/Lamivudine 60/30mg, tablets, 30 Tabs                           | Abacavir/Lamivudine 60/30mg, tablets, 60 Tabs                                     |       0.9716 | digits only  |
| E0089 / E0090  | Lamivudine/Nevirapine/Stavudine 150/200/30mg, tablets, 60 Tabs          | Lamivudine/Nevirapine/Stavudine 150/200/40mg, tablets, 60 Tabs                    |       0.9624 | digits only  |
| E0007 / E0008  | Abacavir/Lamivudine 60/30mg, tablets, 60 Tabs                           | Abacavir/Lamivudine 600/300mg, tablets, 30 Tabs                                   |       0.9595 | digits only  |
| E0042 / E0043  | Emtricitabine/Tenofovir Disoproxil Fumarate 200/300mg, tablets, 30 Tabs | Emtricitabine/Tenofovir Disoproxil Fumarate 200/300mg [Truvada], tablets, 30 Tabs |       0.9593 | letters only |
| E0118 / E0119  | Nevirapine 10mg/ml, oral suspension w/syringe, Bottle, 100 ml           | Nevirapine 10mg/ml, oral suspension w/syringe, Bottle, 240 ml                     |       0.9543 | digits only  |
| E0025 / E0027  | Didanosine 200mg, delayed-release capsules, 30 Caps                     | Didanosine 250mg, delayed-release capsules, 30 Caps                               |       0.9541 | digits only  |
| E0131 / E0132  | Ritonavir 100mg [Norvir], film coated tablets, 30 Tabs                  | Ritonavir 100mg [Norvir], film coated tablets, 60 Tabs                            |       0.9521 | digits only  |
| E0022 / E0024  | Didanosine 100mg, chewable/dispersible tablets, 60 Tabs                 | Didanosine 200mg, chewable/dispersible tablets, 60 Tabs                           |       0.9503 | digits only  |
| E0095 / E0096  | Lamivudine/Stavudine 150/30mg, tablets, 30 Tabs                         | Lamivudine/Stavudine 150/30mg, tablets, 60 Tabs                                   |       0.9498 | digits only  |

## Deviations from the original plan

- The initial context listed five seeds as the default. The owner specified ten seeds, 0–9, for the final run.
- The owner selected the product-group key and added the 20-record cap before the final run.
- The owner specified the one-sided paired test, Holm adjustment, t intervals, and descriptive treatment of original-text exact matching. The Phase 4.5 decision retained the three methods, composite primary field set, connected components, and original cutoff grid.
- The final run regenerated preparation files in a temporary copy to preserve repository inputs. The 72 regenerated files matched the saved preparation files byte for byte. Report labels use the wording approved in Phase 6b.
- The frozen experiment settings and metric definitions were used throughout Phase 7.

## Files produced

- [Test scores](../backend/app/results/rq1/raw_runs.csv) with 320 rows, [validation tuning scores](../backend/app/results/rq1/tau_selection.csv) with 3,200 rows, and [run metadata](../backend/app/results/rq1/metadata.json).
- Five [tables](../backend/app/results/rq1/tables/) in CSV, Markdown, and LaTeX, and two [figures](../backend/app/results/rq1/figures/) in PNG.
- [Observed H1 check](../backend/app/results/rq1/h1_check.md), this results note, and the [architecture update](ARCHITECTURE.md).
- [Results validator](../backend/app/experiments/rq1/validate_rq1_results.py) and its [tests](../backend/app/tests/rq1/test_validate_rq1_results.py).

## Post-hoc analyses (designed after seeing the frozen results)

The frozen fuzzy method lost precision when it grouped products whose descriptions differed by a number. The frozen validation splits also contained fewer look-alike product pairs than the test splits. We explored whether requiring exact agreement on the structured fields would prevent those errors and whether an even split would give the cutoff more representative validation data. Both analyses reuse the same noisy records and ten seeds. Their results are exploratory and the original H1 outcome above stands.

- **P1, 30% validation and 70% test.** We reused the frozen entity splits and added a fuzzy method that first requires agreement on cleaned dosage, dosage form and pack size. It then compares descriptions with the existing Bloom filter and groups connected records as before. All 320 original test result rows matched the frozen data after excluding runtime, and all 3,200 original validation tuning rows matched exactly.
- **P2, 50% validation and 50% test.** We ran the same four methods with a separate entity split for each seed. Of the 26 look-alike product pairs identified in the frozen descriptive profile, an average of 5.9 fell together in validation and 6.9 in test, compared with 1.8 and 14.0 in P1. Both fuzzy methods chose their main cutoff on validation only, using the same grid and one cutoff across typo levels.

### Post-hoc analysis comparisons with cleaned-text exact matching

F1 scores are held-out means across ten seeds. The existing methods in this comparison use all four fields. Blocked fuzzy matching compares descriptions within the structured-field blocks. Each fuzzy method has its own Holm correction across the three positive typo levels within each run. Wins count seeds where the fuzzy method scored higher than the cleaned-text baseline.

| Run | Share of records with typos | Cleaned-text exact F1 | Pure fuzzy F1 | Pure fuzzy wins / adjusted p | Blocked fuzzy F1 | Blocked fuzzy wins / adjusted p |
| --- | --------------------------: | --------------------: | ------------: | ---------------------------: | ---------------: | ------------------------------: |
| P1  |                          5% |                 0.909 |         0.786 |                2/10 / 1.0000 |            0.987 |                  10/10 / 0.0029 |
| P1  |                         15% |                 0.811 |         0.770 |                5/10 / 1.0000 |            0.987 |                  10/10 / 0.0029 |
| P1  |                         30% |                 0.649 |         0.757 |                8/10 / 0.0293 |            0.987 |                  10/10 / 0.0029 |
| P2  |                          5% |                 0.906 |         0.916 |                8/10 / 0.1875 |            0.994 |                  10/10 / 0.0029 |
| P2  |                         15% |                 0.809 |         0.890 |                9/10 / 0.0039 |            0.994 |                  10/10 / 0.0029 |
| P2  |                         30% |                 0.647 |         0.849 |               10/10 / 0.0029 |            0.991 |                  10/10 / 0.0029 |

In P1, blocking raised fuzzy precision at the three typo levels from about 0.70 to about 0.98, with recall close to 1.00. Blocked fuzzy matching exceeded the 0.90 F1 target at 5% in both runs and beat the cleaned-text baseline in all ten seeds at each typo level. In P2, pure fuzzy matching also reached 0.90 at 5% and had a higher mean F1 than the cleaned-text baseline at all three levels. Its adjusted p-value was above 0.05 at 5% and below 0.05 at 15% and 30%.

**Limitations.** Dosage, form and pack size carried no typos in this experiment and also help define the product groups used for evaluation. P1 is therefore an optimistic best case for blocking. In practice, errors in these fields could prevent the method from comparing records from the same product. Absolute scores depend on split size. For a randomly allocated set of products, the expected number of look-alike pairs inside a split grows roughly with the square of the share assigned to it. P2 changed both the data available for tuning and the pairs available for testing, so the score change cannot be attributed to cutoff selection alone.

- **Post-hoc analysis P1** · [F1](../backend/app/results/rq1_posthoc/p1_blocked_split3070/tables/table1_f1_by_noise.md) · [Precision, recall and fragmentation](../backend/app/results/rq1_posthoc/p1_blocked_split3070/tables/table2_fragmentation_precision.md) · [Paired differences](../backend/app/results/rq1_posthoc/p1_blocked_split3070/tables/table5_paired_difference.md) · [F1 figure](../backend/app/results/rq1_posthoc/p1_blocked_split3070/figures/fig1_f1_vs_noise.png) · [Fragmentation figure](../backend/app/results/rq1_posthoc/p1_blocked_split3070/figures/fig2_fragmentation_vs_noise.png)
- **Post-hoc analysis P2** · [F1](../backend/app/results/rq1_posthoc/p2_split5050/tables/table1_f1_by_noise.md) · [Precision, recall and fragmentation](../backend/app/results/rq1_posthoc/p2_split5050/tables/table2_fragmentation_precision.md) · [Paired differences](../backend/app/results/rq1_posthoc/p2_split5050/tables/table5_paired_difference.md) · [F1 figure](../backend/app/results/rq1_posthoc/p2_split5050/figures/fig1_f1_vs_noise.png) · [Fragmentation figure](../backend/app/results/rq1_posthoc/p2_split5050/figures/fig2_fragmentation_vs_noise.png)
