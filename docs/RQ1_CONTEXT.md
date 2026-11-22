# RQ1 Context

## 1. Project

Final-year research project. Component 1: "Pre-ledger cross-organizational data harmonization and entity resolution using differentially private Bloom filters" (Big Data dimension: Veracity). This file covers RQ1 only. RQ2 (privacy) and RQ3 will reuse the same common code later, so reusable code must live in src/common/.

RQ1: Under varying levels of input data errors (5%, 15%, 30%), does Bloom filter-based fuzzy matching (character q-grams + keyed Bloom filter + Dice similarity) achieve significantly higher F1 and lower data fragmentation than exact matching (SHA-256) for entity linking?
H0: at 5%, 15%, 30% noise, fuzzy F1 is not higher than exact F1.
H1: at 5%, 15%, 30% noise, fuzzy F1 is higher than exact F1, and at 5% noise fuzzy F1 >= 0.90.
Do NOT claim F1 >= 0.90 at 30% noise. 0% noise is a control only and is not part of the H1 claim.
Differential privacy is NOT part of RQ1.

## 2. Study design (fixed, do not change without asking)

Datasets

- Raw dataset: original CSV in data/raw/ (never modified).
- Base dataset = prepared raw data (empty rows removed, columns fixed) plus a ground-truth entity_id per record. The base dataset is also the 0% noise control.
- Noisy datasets: copies of the base dataset with noise 5%, 15%, 30%. Total 4 noise levels: 0, 5, 15, 30.
- entity_id is an answer key. No linking method may read it. It is used only for splitting and for computing metrics. The runner must drop entity_id before calling any Linker.

Noise model (record-level)

- Exactly round(p \* n) records are selected without replacement (p in {0.05, 0.15, 0.30}); each selected record gets 1 or 2 typos (random choice), each typo being substitute, delete, insert or transpose, applied to configured text fields only (default: raw_item_description). Numeric strings such as dosage values are not mutated. entity_id and record_id never change. Unselected records stay unchanged.

Split

- Entities (not records) are split into validation and test (default 30/70), per seed. All records of one entity go to the same split. The same split is used for all noise levels. Pairs are only formed inside one split.

Methods (all run on the same noisy datasets)

- raw_exact: raw text -> SHA-256 -> equal hash means same entity.
- normalized_exact: normalize (lowercase, remove all whitespace and punctuation, keep letters and digits only) -> SHA-256.
- bloom_fuzzy: normalize -> q-grams (q=2) -> keyed Bloom filter (HMAC-SHA256, l=1024, k=4) -> Dice >= tau.
  Field sets (applies to every method, so the comparison is fair)
- description: raw_item_description only.
- composite: raw_item_description + dosage + dosage_form + pack_size concatenated with a fixed separator.
- Primary comparison is on the composite field set (pre-specified; do not switch afterwards). The description field set is the ablation.
- Do NOT call the composite variant "hybrid". "Hybrid" is reserved for a possible later variant (name-only Bloom filter + deterministic dosage token blocking).

Threshold tau (bloom_fuzzy only)

- Tuned on the validation split only. Grid 0.60 to 0.99 step 0.01.
- Main result: ONE tau per (seed, field set), chosen to maximize the mean F1 across the four noise levels on validation.
- Sensitivity result: one tau per (seed, field set, noise level), reported in a separate table.
- Ties: choose the higher tau.
- Reported metrics always come from the test split.

Clustering and metrics

- Every method outputs a cluster label per record (exact: identical hash = same cluster; bloom_fuzzy: connected components of pairs with Dice >= tau).
- Pairwise Precision, Recall, F1 are computed from cluster membership versus entity_id over all record pairs inside the split.
- Fragmentation rate: for each true entity with >= 2 records, count the distinct predicted clusters its records fall into; report the mean over those entities (1.0 is best). Always report it together with Precision, because over-merging lowers fragmentation.
- Also record n_records, n_entities, n_pred_clusters, runtime_sec.

Repetition

- Seeds 0..4 by default (config allows up to 10). A seed controls noise generation and the split. Report mean and std across seeds. The HMAC key is fixed in config and identical on both sides of every comparison.

## 3. Shared contracts (all phases must follow these)

- Record table: pandas DataFrame with unique column record_id, column entity_id (ground truth), and text columns. Column names come from config, never hard-coded in algorithms.
- Linker protocol (src/common/linking/base.py): attribute name: str; method link(df: DataFrame) -> pandas Series of integer cluster labels indexed by record_id. Linkers must not access entity_id.
- Metrics (src/common/evaluation/metrics.py): evaluate_clusters(entity_ids: Series, cluster_labels: Series) -> dict with precision, recall, f1, fragmentation_rate, n_records, n_entities, n_pred_clusters.
- Config: dataclasses loaded from YAML (configs/base.yaml, configs/rq1.yaml). rq1.yaml overrides base.yaml.
- Seeding: one helper make_rng(seed, purpose) returning a numpy Generator; the same (seed, purpose) always gives the same stream. No global random state.
- Results: tidy long-format CSV results/rq1/raw_runs.csv with columns: run_id, seed, noise_level, method, field_set, tau, tau_mode (single or per_noise), split, precision, recall, f1, fragmentation_rate, n_records, n_entities, n_pred_clusters, runtime_sec. Every run also writes metadata.json (config snapshot, seeds, library versions, git commit if available, timestamp).
- Bloom filter: q-grams are a set with start/end padding (pad char configurable). Bit positions: for i in range(k), idx_i = int.from_bytes(HMAC_SHA256(key, f"{i}:{qgram}")[:4], "big") % l. l must be a power of two. Works for any k so RQ2 can use k=30. Store filters as numpy uint8 bit arrays.
- Dice: 2\*|A AND B| / (|A| + |B|), vectorized with numpy for all pairs in a split (no Python loops over pairs). If |A|+|B| = 0, similarity = 0.
- Extension hook: the Bloom filter encoder accepts an optional post_transform callable applied to the finished bit array (default None). RQ2/RQ3 plug differential-privacy bit flipping in there. RQ1 never sets it.

## 4. Folder layout (keep exactly; do not rename existing folders)

RP-Component1/
docs/ RQ1*CONTEXT.md, ARCHITECTURE.md
backend/
requirements.txt
app/
main.py (do not modify)
configs/ base.yaml, rq1.yaml
data/ raw/ (read-only) ; generated/ prepared/ , splits/ , noisy/
src/common/
config.py, seeding.py, paths.py
data/ schema.py, loader.py, preparation.py, splitting.py
noise/ typo_noise.py
preprocessing/ normalizer.py, field_builder.py
encoding/ qgrams.py, bloom_filter.py
similarity/ dice.py
linking/ base.py, exact.py, bloom.py, clustering.py, threshold.py
evaluation/ metrics.py, aggregation.py
experiment/ runner.py, metadata.py, io.py
reporting/ tables.py, figures.py
experiments/ rq1/ prepare_rq1_data.py, rq1_methods.py, run_rq1.py, build_rq1_report.py ; rq2/ (existing) ; rq3/ (future)
results/ rq1/ raw_runs.csv, tau_selection.csv, metadata.json, tables/, figures/
tests/ common/ (one test*<module>.py per common module) ; rq1/ ; rq2/ (existing) ; test_experiment_metadata.py (existing)
blockchain/ (do not touch)

## 5. Engineering rules

- Python 3.13 (existing venv313). Allowed libraries: standard library (hashlib, hmac, json, pathlib, dataclasses, argparse), numpy, pandas, scipy (only scipy.sparse.csgraph for connected components), pyyaml, matplotlib, pytest. Anything else needs a written justification first.
- Type hints and short docstrings on public functions. snake*case modules, PascalCase classes, one responsibility per module. Test file name: test*<module>.py.
- No hard-coded paths, column names, seeds or hyper-parameters inside algorithms; they come from config.
- Do not copy code between RQ folders. If RQ2 needs something, it goes in src/common/.
- Do not modify data/raw/, blockchain/, or main.py. Do not delete existing RQ2 code or tests; if existing code must change, say exactly why.
- No abstract base class hierarchies, plugin registries, databases, web UI or async code. Keep it simple.
- Every phase ends with: all new tests pass, all existing tests still pass (pytest from backend/), a short summary of files created or changed, and an update to docs/ARCHITECTURE.md.
- Do not start work belonging to a later phase. If a later-phase need appears, leave a short TODO note in the summary instead of implementing it.
- If something in this context is ambiguous or conflicts with the existing code, stop and ask before guessing.
