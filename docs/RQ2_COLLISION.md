# RQ2 empirical collision benchmark

Use the dedicated profile in `backend/app/configs/rq2_collision.yaml`. The runner reads the same prepared dataset and description-noise files as RQ1. It first replays at 15% noise against the frozen RQ1 result files, using the original splits, public fixture key and per-seed cutoff. The main benchmark uses independent three-way splits by entity and paired noise and keys within each seed.

From the repository root in PowerShell, install the development dependencies if needed and run the benchmark with an environment-supplied `RQ2_HMAC_ROOT_KEY`. The value must be at least 32 private bytes encoded as hex. Use the same externally supplied value to reproduce an existing run. Only seed-key fingerprints appear in metadata. The benchmark never writes the key.

```powershell
.\backend\venv313\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
$env:PYTHONPATH = 'backend/app'
.\backend\venv313\Scripts\python.exe -m experiments.rq2.collision_runner
```

Use `--stage gate` to check the frozen metrics without requiring the RQ2 key, and `--stage controls` to check the frequency controls. `--extended` uses the extended grid and writes to a separate subdirectory. The default primary grid contains 12 cells.

For the optional 15% all-fields row, first prepare the variant with the original generator, then pass `--all-fields`.

```powershell
.\backend\venv313\Scripts\python.exe -m experiments.rq1.prepare_rq1_data --stage noise --all-fields --seeds 0 1 2 3 4 --noise-levels 15
.\backend\venv313\Scripts\python.exe -m experiments.rq2.collision_runner --all-fields
```

The default output directory is `backend/app/results/rq2/`. `summary.md` describes the threat model, measurement definitions, limitations and seed-level variation. `recommendation.json` contains the selected `l` and `k` for a future RQ3 run. The legacy RQ2 grid, analyzer and profiler are deprecated and remain callable. RQ3 retains its existing epsilon-sweep setup.

## Selection and comparisons

The pilot used 27 validation and 33 reference entities sampled from seed 0's corresponding main partitions. It evaluated no seed-0 test records for selection. The best eligible pilot point was Baseline 2, with validation F1 0.99123 and attack success 0.00263. The observed relative improvement was zero. The configured minimum positive pilot threshold is a single 5-percentage-point step. The pilot therefore froze a 5% relative reduction target and a 0.05 absolute F1 budget in commit `f34a971`.

Every Bloom configuration uses its own best validation F1 cutoff, with ties going to the higher cutoff. Baseline 2 alone also reports the historical RQ1 cutoff. The keyed normalized exact baseline groups the same observations by equality of HMAC-SHA256 digests, with no cutoff. The recommendation uses seed-averaged validation attack success subject to the validation F1 floor. An eligible near-tie has a paired validation attack-success interval against the recommendation that includes zero. The lowest-attack validation point across the unrestricted grid is the extreme. If roles share a point, they share that robustness run. Held-out rows and Pareto membership are descriptive.

The reference comes from disjoint entities in the prepared data. The empirical measurement uses one frequency-alignment attack and reports only aggregate results. The known-key view uses analytical occupancy and per-bit membership ambiguity. RQ3 addresses formal differential privacy.

## Shared statistics

The frozen RQ1 report uses the shared `paired_difference` function for paired means, t intervals and its prespecified tests. It does not call the legacy `paired_effect` function that mislabeled sign balance as rank-biserial. The new benchmark uses signed ranks, distinct Walsh averages for Hodges–Lehmann, and paired seed resampling with zero differences retained. It reports no p-values.
