# RQ1 architecture audit

Phase 0 · 22 November 2026 · [Study design](RQ1_CONTEXT.md)

Paths are relative to `backend/app/` unless stated otherwise. The audit describes the working tree as found, including pre-existing edits. The mapping and archive entries are proposals. The entity rules were evaluated in memory without assigning IDs to repository data.

## Legacy plan

The results tree contains 26 local, Git-ignored files. In the list below, `{,_record_level}` denotes the two observed versions of each stem.

| Existing location | Files | Proposed archive destination |
| --- | --- | --- |
| `results/rq1/raw/` | `rq1_accuracy_benchmark_raw_per_seed{,_record_level}.csv`, `rq1_threshold_tuning_raw_per_seed{,_record_level}.csv` (4) | `results/rq1_legacy/raw/` |
| `results/rq1/tables/` | `rq1_accuracy_benchmark_aggregated{,_record_level}.csv`, `rq1_wilcoxon_comparisons{,_record_level}.csv`, `rq1_tau_policies{,_record_level}.csv`, `rq1_headline_table{,_record_level}.{csv,tex}`, `rq1_oracle_threshold_table{,_record_level}.{csv,tex}` (14) | `results/rq1_legacy/tables/` |
| `results/rq1/figures/` | `rq1_accuracy_vs_noise{,_record_level}.{pdf,png}`, `rq1_threshold_sensitivity{,_record_level}.{pdf,png}` (8) | `results/rq1_legacy/figures/` |
| `data/generated/` | `clean_master_products.csv` (481 records, 149 entities), `entity_catalog.csv` (149 rows), `ground_truth_pairs.csv` (1,150 positive pairs across 96 entities) | `results/rq1_legacy/generated/` |
| `data/generated/` | `noisy_products_{0,5,15,30}_seed{42..56}.csv` (60 tracked files) | `results/rq1_legacy/generated/` |

Each observed raw accuracy CSV has 1,080 rows for reporting seeds 47–56. Each observed threshold tuning CSV has 540 rows for seeds 42–46. The runner can also write a bootstrap CSV and the simulator can write `cross_org_simulation.csv`. Neither was present.

Archive the 26 results before the first new run and reserve `results/rq1/` for the new output contract. Before relocating generated data, pin the RQ2 runners and fixture test to a stable legacy data location in an authorized phase. The RQ2 grid and DP ablation default to the current master and noise paths, and `test_controlled_noise_loader_aligns_rq1_files` reads both. Until that path dependency is addressed, retain those tracked inputs at the current paths and have new RQ1 read only from the prescribed `data/generated/prepared/`, `splits/` and `noisy/` subdirectories. An archive manifest should preserve filenames, checksums and the distinction between the two legacy noise modes. Configure any future execution of the legacy runner to write under the archive so it cannot repopulate the new results directory.

## Inventory

The walk found 48 Python modules and no Python under `data/` or `results/`. Sections above and below detail the data and outputs. `backend/requirements.txt` declares the combined application and research dependencies. There is no `app/configs/` directory or prescribed shared subpackage tree in the audited layout. Public API below means locally defined non-underscore functions and classes, with public methods or properties in parentheses. Constants, imported symbols and demo functions inside `__main__` guards are omitted.

| Module | Serves | Purpose | Public functions and classes |
| --- | --- | --- | --- |
| `__init__.py` | Shared | Package marker for the backend application. | None |
| `experiments/__init__.py` | Shared | Package marker for experiment entry points. | None |
| `experiments/rq1/__init__.py` | RQ1 | Marks the RQ1 experiment package. | None |
| `experiments/rq1/grid_runner.py` | RQ1 | Runs legacy accuracy sweeps and generates statistical summaries, reports and plots. | `Experiment1AccuracyBenchmark(execute_benchmark, select_threshold, select_threshold_per_noise, save_tau_policies, statistical_comparison, entity_bootstrap_comparison, aggregate, headline_table, oracle_threshold_table, plot_headline, plot_threshold_sensitivity), main` |
| `experiments/rq1/noise_dataset_generator.py` | RQ1, RQ2 fixtures | Generates seeded CSVs with character-rate typos. | `SyntheticNoiseGenerator(generate_noisy_datasets)` |
| `experiments/rq2/__init__.py` | RQ2 | Marks the RQ2 experiment package. | None |
| `experiments/rq2/dataset_profiler.py` | RQ2 | Profiles source data and estimates Bloom-filter saturation. | `main` |
| `experiments/rq2/dp_ablation_runner.py` | RQ2 | Runs the differential privacy ablation. | `main` |
| `experiments/rq2/grid_runner.py` | RQ2 | Runs the RQ2 experiment grid and exact baseline. | `work, print_entity_weights, main` |
| `experiments/rq2/results_analyzer.py` | RQ2 | Aggregates RQ2 runs and produces inference, operating points and plots. | `ci95, aggregate, heatmap, pareto_front, holm_bonferroni, paired_effect, merge_paired, load_run_meta, validate_run_metas, main` |
| `main.py` | Application, outside RQ1 | Exposes harmonization, health and ledger endpoints. | `HarmonizeRequest, HarmonizeResponse, get_pipeline, health, harmonize, ledger_summary` |
| `src/__init__.py` | Shared | Marks the source package. | None |
| `src/application_config.py` | RQ1, RQ2, application | Loads environment settings, experiment defaults and application paths. | `ExperimentConfig, Config(ensure_directories)` |
| `src/common/__init__.py` | Shared | Marks the existing shared package. | None |
| `src/common/experiment_metadata.py` | RQ2, shared helpers | Provides experiment CLI options, fingerprints, version metadata and output writers. | `add_common_args, parse_standard, data_fingerprint, package_versions, config_metadata, write_run_csv, write_markdown` |
| `src/common/keyed_bloom_filter.py` | RQ1 legacy, application | Encodes keyed bitarrays and provides ledger serialization helpers. | `KeyedBloomFilter(encode, calculate_bit_density, to_bytes, to_hex, from_bytes, from_hex)` |
| `src/common/noise_injection.py` | RQ1 legacy, RQ2 | Implements legacy character edits and an edit-distance helper. | `NoiseSpec, mutate_once, add_typos, add_noise, levenshtein, inject_typo` |
| `src/common/preprocessor.py` | RQ1 legacy, application | Normalizes delimited text, parses attributes and delegates q-gram extraction. | `TextPreprocessor(normalize, extract_qgrams, extract_token_qgrams, extract_token_qgrams_list, parse_attributes_from_text, extract_composite_qgrams, compare_token_overlap)` |
| `src/common/qgram_extractor.py` | RQ1 legacy, application | Builds globally padded, token-based and tagged composite q-grams. | `QGramExtractor(pad_token, extract_from_token, extract_token_qgrams, extract_token_qgrams_list, extract_global_qgrams, extract_composite_qgrams, compare_token_overlap)` |
| `src/rq1/__init__.py` | RQ1 | Marks the legacy RQ1 source package. | None |
| `src/rq1/cross_org_simulator.py` | RQ1 legacy | Replicates master records across three simulated organization styles. | `CrossOrgSimulator(generate_cross_org_dataset)` |
| `src/rq1/dice_similarity.py` | RQ1 legacy, application | Computes bitarray Dice and Jaccard and searches leader candidates. | `DiceSimilarityEngine(calculate_dice, calculate_jaccard, find_best_candidate)` |
| `src/rq1/entity_resolver.py` | RQ1 legacy | Assigns incoming records to immutable representative filters. | `ClusterEntity(add_member), EntityResolver(get_candidate_filters, resolve_record, process_dataset, reset)` |
| `src/rq1/exact_matcher.py` | RQ1 | Hashes text and groups identical hashes into stateful clusters. | `ExactMatcher(compute_hash, resolve_record, process_dataset, reset)` |
| `src/rq1/record_linkage_metrics.py` | RQ1 | Computes pairwise cluster scores and entity bootstrap intervals. | `LinkageMetrics(compute_pairwise_metrics, format_metrics_table, entity_bootstrap_ci)` |
| `src/rq1/shipment_data_loader.py` | RQ1 legacy, RQ2 fixtures | Prepares a deduplicated master, clinical entity catalog and ground-truth pair export. | `SupplyChainDataLoader(basic_clean_text, load_raw_dataset, extract_clean_master, generate_ground_truth_pairs, run)` |
| `src/rq2/__init__.py` | RQ2 | Marks the RQ2 source package. | None |
| `src/rq2/bitarray_differential_privacy.py` | RQ2, application | Applies randomized response to bitarrays. | `LocalDifferentialPrivacy(calculate_flip_probability, apply_randomized_response, batch_apply_ldp, verify_empirical_flip_rate)` |
| `src/rq2/blockchain_client.py` | Application, outside RQ1 | Reads and writes ledger records and supports a mock ledger. | `BlockchainClient(retrieve_stored_candidates, commit_harmonized_record, verify_record_exists, get_record, reset_mock_state, get_ledger_summary)` |
| `src/rq2/bloom_encoder.py` | RQ2 | Encodes batches as keyed NumPy bit arrays with double hashing. | `BloomEncoder(gram_positions, encode_many, encode)` |
| `src/rq2/experiment_config.py` | RQ2 | Aliases shared experiment defaults and declares the RQ2 grid. | None |
| `src/rq2/harmonization_pipeline.py` | Application, RQ2 privacy mechanism | Orchestrates preprocessing, encoding, privacy, ledger matching and commits. | `HarmonizationPipeline(synchronize_with_ledger, process_single_record, process_batch, reset)` |
| `src/rq2/numpy_randomized_response.py` | RQ2 | Applies NumPy randomized response to Bloom arrays. | `flip_probability, randomized_response` |
| `src/rq2/parameter_validation.py` | RQ2 | Validates RQ2 parameters, datasets and dictionaries. | `validate_tau, validate_bloom_parameters, validate_eps, validate_noise, validate_overlap, validate_n_records, validate_bit_top, validate_dataset, validate_dictionary` |
| `src/rq2/privacy_attacks.py` | RQ2 | Implements privacy evaluation routines for reidentification, frequency and bit analysis. | `reid_attack, exact_reid_attack, frequency_attack, bit_qgram_attack` |
| `src/rq2/privacy_metrics.py` | RQ2 | Measures bit saturation, entropy, collision load and effective noise. | `fill_stats, bit_entropy, collision_load, expected_fill, effective_noise` |
| `src/rq2/privacy_pipeline.py` | RQ2 | Builds paired scenarios and evaluates Bloom and exact configurations. | `Scenario, build_scenario, run_bloom, run_exact` |
| `src/rq2/qgram_utils.py` | RQ2 | Extracts whole-string q-grams as lists or sets. | `qgrams, qgram_set` |
| `src/rq2/results_schema.py` | RQ2 | Validates RQ2 experiment output tables. | `SchemaError, validate_results` |
| `src/rq2/rq2_dataset.py` | RQ2 | Loads, samples and aligns synthetic, real and controlled-noise data. | `Dataset(n), synthetic_dataset, resolve_columns, csv_dataset, load_dataset, controlled_noise_dataset, apply_real_frequency_counts` |
| `src/rq2/similarity_matching.py` | RQ2 | Computes vectorized Dice and two-party threshold, linkage and separation metrics. | `dice_matrix, sweep, tune_tau_full, tune_tau, metrics_at, auc_and_separation, exact_metrics` |
| `src/rq2/text_normalizer.py` | RQ2 | Canonicalizes descriptions for the RQ2 encoding and exact baseline. | `normalize` |
| `tests/common/test_qgrams.py` | Shared, legacy RQ1 representation | Tests token boundaries, optional composite fields and delimiter handling. | `test_composite_qgrams_ignore_none_attributes, test_common_qgram_extraction_uses_token_boundaries, test_common_preprocessor_normalizes_delimiters` |
| `tests/rq1/test_rq1_correctness.py` | RQ1 | Tests raw SHA-256 whitespace handling and bootstrap interval output. | `test_raw_exact_matching_does_not_strip_input, test_entity_bootstrap_returns_metric_intervals` |
| `tests/rq2/test_pipeline.py` | RQ2 | Tests paired scenarios, benchmark behavior and legacy RQ1 fixture integration. | `test_scenarios_are_reproducible_and_paired, test_rows_have_all_columns_and_valid_ranges, test_no_noise_exact_matching_is_perfect_and_bf_is_close, test_noisy_exact_hash_without_dictionary_matches, test_fuzzy_beats_exact_under_noise, test_collision_tuning_trades_utility_for_privacy, test_rq2_run_bloom_has_no_dp_fields, test_controlled_noise_loader_aligns_rq1_files, test_real_frequency_weights_join_normalized_descriptions, test_saturated_config_produces_row_with_f1_unc, test_no_nan_in_f1_unc_multiple_configs` |
| `tests/rq2/test_units.py` | RQ2 | Tests normalization, encoding, similarity, privacy and attack metrics. | `test_normalize_variants_collapse, test_real_dataset_description_and_composite_aliases, test_qgrams, test_positions_distinct_and_in_range, test_positions_distinct_for_non_power_of_two_lengths, test_encoder_deterministic_and_keyed, test_encode_many_matches_single_and_handles_duplicates, test_fill_matches_theory, test_dice_properties, test_threshold_tuning_and_metrics, test_tune_tau_full_basic, test_tune_tau_full_saturated_infeasible, test_tune_tau_never_raises_on_saturated, test_exact_metrics, test_noise_changes_strings_at_requested_rate, test_dp_flip_rate, test_reid_attack_collisions_reduce_success, test_reid_attack_respects_dictionary_coverage, test_exact_reid_attack, test_frequency_attack_perfect_with_distinct_frequencies, test_bit_qgram_attack_runs_and_beats_baseline_at_low_collision, test_structural_metrics` |
| `tests/rq2/test_validation.py` | RQ2 | Tests parameter ranges, data boundaries, schemas and analysis helpers. | `test_invalid_eps, test_extreme_eps, test_noise_bounds, test_overlap_bounds, test_invalid_n_records, test_invalid_bit_top, test_small_dataset, test_noise_short_strings, test_shared_noise_vendor_present, test_rq2_tau_boundaries, test_rq2_tau_outside_bounds, test_rq2_bloom_parameter_boundaries, test_rq2_bloom_parameters_outside_bounds, base_schema_df, test_schema_missing_columns, test_schema_duplicate_records, test_schema_invalid_nan, test_schema_rejects_finite_candidate_counts_below_one, test_schema_imbalanced_seeds, test_holm_known_example, test_paired_seed_alignment` |
| `tests/test_experiment_metadata.py` | Shared, RQ2 helper use | Tests Markdown output with tabulate support and its fallback. | `test_markdown_fallback, test_markdown_to_markdown_when_available |` |

## Differences from study design

| Area and legacy source | Observed behavior and required difference |
| --- | --- |
| Base and ground truth · `src/rq1/shipment_data_loader.py` | Guesses headers, trims and collapses descriptions, filters unusable descriptions, substitutes structured sentinels, assigns sequential `REC_*` IDs, and deduplicates by cleaned description plus vendor. The clean master is 481 records from 10,324 shipment rows. The loader applies a normalized molecule/test type + dosage + form + pack key, writes `true_entity_id`, and exports positive pairs. Its docstring says 184 entities, while the checked-in catalog and master contain 149. The fixed design prepares raw rows with configured columns, unique record IDs and an owner-approved `entity_id`. Evaluation uses all pairs within each split. |
| 0% control and file inputs · `experiments/rq1/grid_runner.py`, `noise_dataset_generator.py` | Legacy 0% comes from copies of the deduplicated master or a seed-42/fallback CSV. Positive file-mode inputs are precomputed, and the runner generally accepts them without verifying semantics. In record-level mode it overlays descriptions by record ID and silently uses the clean text if a mapping is missing. The study uses the prepared base itself as 0% and derives all three noisy copies from that base. |
| File noise · `noise_dataset_generator.py`, `src/common/noise_injection.py` | The generator attempts to mutate every row at positive rates. The shared `inject_typo` schedules `max(1, floor(rate × length))` edits and stops at length ≤ 3. Unchanged substitutions, equal-letter swaps and final-position transposes can yield no change. The checked-in copies changed 477–481 of 481 descriptions at 5% and 481 at 15% and 30% across all 15 seeds. The design requires exactly `round(p × n)` distinct rows and a random one or two typos per selected row. |
| Inline and nominal record-level noise · `grid_runner.py` | The inline character loop rounds the edit budget instead of flooring it and allows deletion at lengths the file helper protects. The `record_level` option draws independent Bernoulli flags and replaces chosen descriptions from one fixed-intensity corruption (5% characters by default). Its row count fluctuates and the edits still depend on string length. The study fixes the selected count and typo count distribution independently of string length. |
| Mutation fields and numeric protection · `noise_dataset_generator.py`, `grid_runner.py`, `noise_injection.py` | File generation defaults to description but `--all-fields` also mutates dosage, form and pack. Its configured default all-fields destination aliases the ordinary generated directory, so the same filenames can be overwritten. Inline and record-level modes change description only. The on-disk files preserve structured columns and IDs. Actual edit loops protect no numeric span, including dosage embedded in descriptions, despite the generator docstring. The study uses a configured text-field allowlist with numeric protection and preserves IDs and unselected rows. The NumPy `add_typos` helper used by RQ2 is also character-rate and has no numeric protection. |
| Organization simulation · `src/rq1/cross_org_simulator.py` | Triplicates each master row, adds organization-specific formatting and a 30% typo opportunity for the third organization, reseeds global Python randomness and omits separate dosage and dosage-form columns. The fixed experiment retains the base record set and varies only the specified typos. The legacy grid does not call this simulator. |
| Split and randomness · `grid_runner.py`, `noise_dataset_generator.py`, `src/application_config.py` | Each seed runs over the same whole legacy population, so disjoint tuning and reporting seed lists still reuse entities. There is no entity-disjoint 30/70 split or split-constrained pair generation. File generation uses one Python RNG per seed across noise levels in loop order. Inline noise uses a seed/noise arithmetic offset, Bernoulli selection uses another offset and leader order is shuffled with `Random(seed)`. The CLI defaults to seeds 42–46 for tuning and 47–51 for reporting, with artifacts reporting 47–56. Study seeds default to 0–4, allow up to ten, use purpose-specific NumPy streams, and freeze the entity split across noise levels per seed. |
| Threshold selection · `grid_runner.py` | Legacy grid uses 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.92, 0.94, 0.96 plus configured/fixed thresholds if absent. It selects one global composite tau averaged across tuning seeds and noise levels and applies that cutoff to both fuzzy field sets. Per-noise taus are pooled across tuning seeds by method. Sorted `idxmax` selects the smaller tied tau. A fixed `--tau` can bypass main selection. The oracle chooses on reporting scores directly, and `--seeds` or overlapping lists allow direct tuning/reporting reuse. The study uses 0.60–0.99 by 0.01, higher tau on ties, one main validation tau per seed and field set across four noise levels, and separate per-noise validation selections with test-only reported scores. |
| Exact baselines and field fairness · `grid_runner.py`, `src/rq1/exact_matcher.py`, `src/common/preprocessor.py` | Raw SHA-256 preserves its supplied text byte-for-byte, but only runs on description and can be disabled. The two normalized exact variants use a normalizer that strips inventory prefixes, maps selected punctuation to spaces and preserves word boundaries. Composite exact joins fields with spaces, while composite Bloom uses tagged features. The study crosses all three methods with both field sets using the same field builder, keeps composite primary and description as ablation, and removes all punctuation and whitespace for normalized methods. RQ2's `text_normalizer.py` is closer, but explicitly decomposes Unicode and restricts output to ASCII. |
| Q-grams · `grid_runner.py`, `src/common/preprocessor.py`, `qgram_extractor.py` | Both Bloom variants call the composite helper. In the description branch, passing `None` for structured fields triggers parsing dosage, form and pack from the description. The helper mixes tagged token bigrams and trigrams for the name, pads each token, and adds weighted dosage, exact structure tags and missing-dosage tags. Common legacy defaults use q=3 in code. The study calls for one set of globally padded q=2 character grams from each normalized field-set string, with a configurable pad and without special tags or inferred extra features. The existing global set extraction is a reuse candidate. |
| Keyed encoding · `src/common/keyed_bloom_filter.py`, `src/rq2/bloom_encoder.py` | Legacy RQ1 has compatible fallback length 1024 and hash count 4, but accepts environment overrides without power-of-two validation, uses `bitarray`, resolves a key from environment or fallback, and hashes `qgram:i` with an eight-byte prefix. RQ2 stores NumPy uint8 and batches repeated strings, but uses one HMAC per gram with double hashing, allows non-power-of-two lengths and defaults to no padding. Neither exposes the required post-transform. The study uses a fixed configuration key and HMAC-SHA256 over `i:qgram` with a four-byte prefix modulo the power-of-two length, padded sets, NumPy uint8, and an optional finished-array transform reserved for future RQs. Legacy RQ1 already omits differential privacy. |
| Dice and clustering · `src/rq1/dice_similarity.py`, `entity_resolver.py` | Ordinary Dice matches the formula, but returns 1.0 for two empty filters. It scans representatives in Python and assigns each row to its best eligible existing leader. Shuffling can change clusters, and above-threshold member-to-member edges do not create transitive links. The study uses vectorized NumPy all-pairs Dice, zero for empty pairs, and connected components over the threshold graph. `src/rq2/similarity_matching.py::dice_matrix` already matches the numerical contract. Its remaining metrics and threshold logic assume two-party diagonal truth and are unsuitable for RQ1. |
| Linker boundary · `grid_runner.py`, `exact_matcher.py`, `entity_resolver.py` | Legacy passes the answer key into batch matchers and includes it in result frames, with string cluster IDs. Exact also retains truth in metadata. Neither uses truth to choose clusters in the observed code, but the linkers receive and read it. The new runner removes `entity_id` before linking and passes only inputs permitted by the contract. Linkers return integer labels indexed by `record_id`. |
| Metrics and inference · `record_linkage_metrics.py`, `grid_runner.py` | Pair counts already use true/predicted cluster contingency counts for the full supplied table. The metric silently drops blank/missing labels, rounds before tuning, uses `f1_score` and returns 1.0 for precision/recall when both positive-pair sets are empty on a nonempty frame. There is no fragmentation, per-run timing or consistently exported record/entity/cluster counts. Legacy bootstrap prefixes predicted IDs by resampled entity, which removes between-entity false-positive pairs in replicates. The runner uses two-sided Wilcoxon for precision, recall and F1, including the 0% control. The study reports test-split pairwise metrics plus the mean distinct predicted clusters among true entities with ≥2 rows, counts and runtime, and limits the directional H1 to 5%, 15% and 30% with the ≥0.90 target at 5% only. |
| Configuration and artifacts · `src/application_config.py`, `grid_runner.py`, `src/common/experiment_metadata.py` | Legacy mixes environment defaults, hard-coded columns, paths, seeds and thresholds with CLI overrides. Raw CSVs use display method names, `threshold`, `noise_level_pct`, `f1_score` and pair counts. They omit `run_id`, `field_set`, `tau_mode`, `split`, fragmentation, counts and runtime. Per-seed mean/std aggregation exists but combines policies differently, and oracle rows appear in the headline. The RQ1 runner emits neither the new `raw_runs.csv`/`tau_selection.csv` contract nor a metadata sidecar. The shared RQ2 writer provides versions, fingerprints and config fragments in `run_meta.json` sidecars and lacks the required RQ1 resolved config, Git commit and timestamp contract. The fixed design uses layered YAML/dataclasses and the prescribed output paths/schema, with main and sensitivity results distinct. |

## Mapping table

Every audited Python module has a proposed disposition. A move targets reusable implementation and allows an import-compatible legacy entry point where existing callers or tests require one.

| Module | Disposition | Reason |
| --- | --- | --- |
| `__init__.py` | leave alone | Preserves the application package. |
| `experiments/__init__.py` | leave alone | Preserves existing module imports. |
| `experiments/rq1/__init__.py` | leave alone | Supports legacy and future entry points. |
| `experiments/rq1/grid_runner.py` | leave alone | Keep the legacy entry point for provenance and reuse aggregation and plotting patterns in the prescribed new modules. |
| `experiments/rq1/noise_dataset_generator.py` | leave alone | Keep the historical fixture generator available while the new preparation entry point adopts the fixed record-level design. |
| `experiments/rq2/__init__.py` | leave alone | Preserves existing entry points. |
| `experiments/rq2/dataset_profiler.py` | leave alone | The profiler measures RQ2 parameters. |
| `experiments/rq2/dp_ablation_runner.py` | leave alone | The ablation is specific to the privacy study. |
| `experiments/rq2/grid_runner.py` | leave alone | Preserve the existing runner and its fixture contract. |
| `experiments/rq2/results_analyzer.py` | leave alone | The analysis depends on RQ2 schemas and policies. |
| `main.py` | leave alone | Explicitly protected and consumed by the application. |
| `src/__init__.py` | leave alone | Preserves existing module imports. |
| `src/application_config.py` | leave alone | Existing callers need their environment settings while new RQ1 uses the prescribed YAML configuration. |
| `src/common/__init__.py` | leave alone | Preserves imports as the shared subpackages grow. |
| `src/common/experiment_metadata.py` | refactor in place | Factor reusable metadata helpers into the prescribed experiment modules while preserving current RQ2 sidecar names and schema. |
| `src/common/keyed_bloom_filter.py` | leave alone | Changing positions or bit layout would disrupt compatibility with stored filters. |
| `src/common/noise_injection.py` | refactor in place | Reuse edit primitives in the new typo-noise module with numeric protection while preserving RQ2 character-rate behavior. |
| `src/common/preprocessor.py` | leave alone | The legacy normalization and tagged representation are used by existing callers. |
| `src/common/qgram_extractor.py` | refactor in place | Extract the reusable globally padded set operation into the prescribed module while keeping token and tagged behavior. |
| `src/rq1/__init__.py` | leave alone | Preserves existing imports. |
| `src/rq1/cross_org_simulator.py` | leave alone | Its transformations support a distinct legacy scenario. |
| `src/rq1/dice_similarity.py` | leave alone | The application uses its bitarray interface and the vectorized RQ2 kernel is the better RQ1 basis. |
| `src/rq1/entity_resolver.py` | leave alone | This is the legacy leader model and connected components require a distinct linker. |
| `src/rq1/exact_matcher.py` | move to src/common/linking/exact.py | Reuse byte-for-byte SHA-256 grouping behind the new label-only interface and preserve the old entry point as needed. |
| `src/rq1/record_linkage_metrics.py` | move to src/common/evaluation/metrics.py | Reuse contingency counts with a Series-based interface and fragmentation while retaining the tested legacy API. |
| `src/rq1/shipment_data_loader.py` | leave alone | Preserve fixture provenance and reuse CSV reading logic in the new loader without applying the legacy deduplication. |
| `src/rq2/__init__.py` | leave alone | Preserves existing imports. |
| `src/rq2/bitarray_differential_privacy.py` | leave alone | The privacy transform is outside RQ1 and serves the bitarray pipeline. |
| `src/rq2/blockchain_client.py` | leave alone | The ledger interface is outside the study. |
| `src/rq2/bloom_encoder.py` | leave alone | RQ2 relies on distinct-position and length behavior, so reuse its array and batching ideas in a separate shared RQ1 encoder. |
| `src/rq2/experiment_config.py` | leave alone | The defaults serve the existing privacy suite. |
| `src/rq2/harmonization_pipeline.py` | leave alone | Preserves the existing API execution path. |
| `src/rq2/numpy_randomized_response.py` | leave alone | RQ2 can later supply this through the optional transform hook. |
| `src/rq2/parameter_validation.py` | leave alone | Its validation ranges are part of the RQ2 contract. |
| `src/rq2/privacy_attacks.py` | leave alone | The evaluation serves RQ2. |
| `src/rq2/privacy_metrics.py` | leave alone | These measures support the privacy study. |
| `src/rq2/privacy_pipeline.py` | leave alone | Its two-party scenario design is specific to RQ2. |
| `src/rq2/qgram_utils.py` | leave alone | Its optional padding and short-string behavior are part of the existing encoding contract. |
| `src/rq2/results_schema.py` | leave alone | The schema is specific to RQ2. |
| `src/rq2/rq2_dataset.py` | leave alone | Preserves the existing fixture schema and paired-data behavior. |
| `src/rq2/similarity_matching.py` | refactor in place | Delegate only the NumPy Dice kernel to src/common/similarity/dice.py while retaining RQ2's diagonal-truth API. |
| `src/rq2/text_normalizer.py` | leave alone | Preserves the RQ2 normalization contract. |
| `tests/common/test_qgrams.py` | reuse as is | Retains coverage of existing preprocessing behavior. |
| `tests/rq1/test_rq1_correctness.py` | reuse as is | Protects the reusable behaviors and legacy APIs. |
| `tests/rq2/test_pipeline.py` | reuse as is | Detects regressions in privacy runs and fixture paths. |
| `tests/rq2/test_units.py` | reuse as is | Protects RQ2 semantics during future shared extraction. |
| `tests/rq2/test_validation.py` | reuse as is | Keeps RQ2 contract coverage. |
| `tests/test_experiment_metadata.py` | reuse as is | Protects both output paths while metadata helpers are extracted. |

The prescribed shared YAML config, path/schema helpers, entity split, field builder, linker protocol, connected components, validation-only tuning and experiment runner have no directly compatible classes to relocate. The results and data rows above cover non-Python artifacts. For `backend/requirements.txt`, the proposed disposition is refactor in place to declare direct dependencies while preserving existing RQ2 and application dependencies.

## Data profile

`data/raw/Suppy_Chain_Shipment_Data.csv` is the only raw file. An inline, read-only pandas 2.3.3 profile using default `read_csv` NA parsing found **10,324 rows × 33 columns**, no all-empty rows, no whitespace-only values and 10,324 unique, nonmissing shipment IDs. The dtype column reports pandas inference without date conversion. Missing counts reflect pandas NA cells. Text placeholders such as `Date Not Captured` remain strings.

The source mapping is `item description` → `raw_item_description`, `dosage` → `dosage`, `dosage form` → `dosage_form`, and `unit of measure (per pack)` → `pack_size`. The unique raw `id` is available as a record identifier. Pack size is the per-pack count or amount, while the product description can distinguish units, presentation and accessories.

| Raw column | Inferred dtype | Missing |
| --- | --- | ---: |
| `id` | int64 | 0 |
| `project code` | object | 0 |
| `pq #` | object | 0 |
| `po / so #` | object | 0 |
| `asn/dn #` | object | 0 |
| `country` | object | 0 |
| `managed by` | object | 0 |
| `fulfill via` | object | 0 |
| `vendor inco term` | object | 0 |
| `shipment mode` | object | 360 |
| `pq first sent to client date` | object | 0 |
| `po sent to vendor date` | object | 0 |
| `scheduled delivery date` | object | 0 |
| `delivered to client date` | object | 0 |
| `delivery recorded date` | object | 0 |
| `product group` | object | 0 |
| `sub classification` | object | 0 |
| `vendor` | object | 0 |
| `item description` | object | 0 |
| `molecule/test type` | object | 0 |
| `brand` | object | 0 |
| `dosage` | object | 1,736 |
| `dosage form` | object | 0 |
| `unit of measure (per pack)` | int64 | 0 |
| `line item quantity` | int64 | 0 |
| `line item value` | float64 | 0 |
| `pack price` | float64 | 0 |
| `unit price` | float64 | 0 |
| `manufacturing site` | object | 0 |
| `first line designation` | bool | 0 |
| `weight (kilograms)` | object | 0 |
| `freight cost (usd)` | object | 0 |
| `line item insurance (usd)` | float64 | 287 |

## entity_id candidates

Candidate counts use all 10,324 shipment rows. Text key components use Unicode case folding and whitespace collapse, preserving punctuation. A missing dosage is an empty key component. Pack size uses the decimal string of the parsed integer. Group by the tuple in each rule. Singleton share is the percentage of entities represented by one shipment row.

| Candidate | Grouping rule | Entities | Min | Median | Max | Single-record entities | Main risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| A · Description identity | `item description` | 184 | 1 | 14.5 | 755 | 23 / 184 (12.50%) | Splits spelling, branding or format variants and defines truth from a field shared by all matchers, favoring exact matching in the clean control. |
| B · Clinical product pack | `molecule/test type`, `dosage`, `dosage form`, `unit of measure (per pack)` | 149 | 1 | 17 | 758 | 17 / 149 (11.41%) | Combines brands and presentations when recorded clinical fields agree, including the syringe example. Missing dosage can hide strength differences. |
| C · Brand-specific product pack | Candidate B fields plus `brand` | 172 | 1 | 15 | 755 | 18 / 172 (10.47%) | Separates generic and brand-labeled equivalents and can still combine packaging variants within one brand. |

Each example lists the raw descriptions observed in that group.

| Candidate | Example entity | Shipment rows | Raw item descriptions |
| --- | --- | ---: | --- |
| A | Nevirapine standard bottle description | 57 | “Nevirapine 10mg/ml, oral suspension, Bottle, 240 ml” |
| A | Nevirapine syringe bottle description | 126 | “Nevirapine 10mg/ml, oral suspension w/syringe, Bottle, 240 ml” |
| A | Determine complete HIV kit description | 577 | “HIV 1/2, Determine Complete HIV Kit, 100 Tests” |
| B | Nevirapine · 10mg/ml · oral suspension · 240 | 195 | “Nevirapine 10mg/ml, oral suspension, Bottle, 240 ml”; “Nevirapine 10mg/ml, oral suspension w/syringe, Bottle, 240 ml”; “Nevirapine 10mg/ml [Viramune], oral suspension, Bottle, 240 ml” |
| B | Didanosine · 100mg · chewable/dispersible tablet · 60 | 34 | “Didanosine 100mg [Videx],chewable tablets, 60 Tabs”; “Didanosine 100mg, chewable/dispersible tablets, 60 Tabs” |
| B | Determine complete HIV kit · missing dosage · test kit · 100 | 577 | “HIV 1/2, Determine Complete HIV Kit, 100 Tests” |
| C | Nevirapine · Generic · 10mg/ml · oral suspension · 240 | 183 | “Nevirapine 10mg/ml, oral suspension, Bottle, 240 ml”; “Nevirapine 10mg/ml, oral suspension w/syringe, Bottle, 240 ml” |
| C | Nevirapine · Viramune · 10mg/ml · oral suspension · 240 | 12 | “Nevirapine 10mg/ml [Viramune], oral suspension, Bottle, 240 ml” |
| C | Didanosine · Videx · 100mg · chewable/dispersible tablet · 60 | 11 | “Didanosine 100mg [Videx],chewable tablets, 60 Tabs” |

**Recommendation for owner review.** Candidate B is the best fit if the unit of linkage is a clinical product pack across organizations. It preserves recorded strength, dosage form and pack count and lets different raw descriptions represent the same entity. It also avoids defining truth from the full text the linkers compare. The 149 count happens to match the legacy catalog, which uses different normalization and a deduplicated record table. The choice remains open pending confirmation that generic, branded and accessory variants should group together and agreement on missing dosage.

## Requirements gaps

| Requested library | Direct declaration in `backend/requirements.txt` | Installed in existing `backend/venv313` |
| --- | --- | --- |
| PyYAML | Missing | 6.0.3 |
| SciPy | Missing | 1.18.1 |
| matplotlib | `>=3.8,<4` | 3.11.2 |
| tabulate | `>=0.9,<1` | 0.10.0 |
| pytest | `>=8,<9` | 8.4.2 |
| pandas | `>=2.2,<3` | 2.3.3 |
| NumPy | `>=2,<3` | 2.5.5 |

PyYAML and SciPy are the two manifest gaps. The context limits new RQ1 SciPy use to `scipy.sparse.csgraph` for connected components. It omits tabulate from its explicit allowlist, while the audit request includes it and the existing metadata helper already supports it. Legacy RQ1 imports seaborn, `scipy.stats`, bitarray and python-dotenv through its current paths. Existing application and RQ2 dependencies need to remain available. No packages were installed.

## Existing test status

Executed the full suite from `backend/` with the existing Python 3.13.17 and pytest 8.4.2. Bytecode and the pytest cache plugin were disabled for both runs. The successful command also used `--basetemp` with a fresh path outside the repository.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$rqAuditTestTemp = Join-Path ([System.IO.Path]::GetTempPath()) ('rq1-phase0-pytest-' + [guid]::NewGuid().ToString('N'))
.\venv313\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $rqAuditTestTemp --tb=short
```

**86 passed, 0 failed, 0 skipped, 0 errors**. The final run collected 86 tests and took 4.06 seconds. There were no failing test names in the final run.

The initial run collected 86 and reported 83 passed, 0 failed, 0 skipped, and three setup errors because the default Windows pytest temp directory could not be read. All three passed with the fresh path.

- `app/tests/rq2/test_pipeline.py::test_real_frequency_weights_join_normalized_descriptions`
- `app/tests/test_experiment_metadata.py::test_markdown_fallback`
- `app/tests/test_experiment_metadata.py::test_markdown_to_markdown_when_available`

## Risks

- **Ground-truth validity.** These keys are proxies inferred from shipment fields. Missing dosage and presentation differences can create systematic labeling errors. Using description itself as truth can also make the clean baseline artificially easy.
- **Split variance and runtime.** Entity sizes range from one to several hundred records. A 30/70 entity split can differ substantially from a 30/70 record split, and large entities dominate pairwise scores. A 70%-of-records example is about 7,227 rows, yielding about 26.1 million unordered pairs and about 398 MiB for a dense float64 Dice matrix alone. Vectorized blocks can preserve all-pairs semantics while bounding peak memory.
- **Connected-component chaining.** An above-threshold edge can join two otherwise separate product groups. Report precision with fragmentation under each noise condition.
- **Noise integrity.** Numeric spans can occur inside the mutable description. A substitution with the original character, a swap of equal characters or two edits that undo each other can undermine the exact selected-record change count.
- **Inference and compatibility.** A two-sided exact Wilcoxon test with five nonzero paired seed differences has a minimum p-value of 0.0625. The tests use the historical RQ2 fixtures, and moving those fixtures before updating their consumers would introduce a separate regression. Neither the observed legacy scores nor the green suite validates the new design.

## Open questions for the owner

1. Which entity definition should RQ1 use? Candidate B is recommended for clinical product packs. Should brands, accessories such as included syringes, and rows with missing dosage be handled differently from that rule?
2. Which directional inferential procedure, significance level and multiple-comparison policy should support H1 under the default five seeds and the SciPy restriction?
3. Is tabulate approved for new RQ1 reporting under the context’s allowlist?
4. What conventions should scores use when there are no positive pairs, or fragmentation when the split contains no repeated entity?
5. Should a later phase relocate the generated legacy inputs after updating RQ2 consumers, or retain them permanently at their current compatibility paths?

The owner decisions below supersede the Phase 0 proposals.

## Owner decisions

1. Set `max_records_per_entity = 20`. Sample without replacement with `make_rng(0, "entity_cap")` when an entity exceeds that cap. Report capped entities and removed rows. Preserve duplicate records subject to the cap.
2. Use seeds 0 through 9 for the final run.
3. In Phase 6, test fuzzy versus `normalized_exact` at 5%, 15% and 30% noise with the one-sided exact Wilcoxon signed-rank test (`scipy.stats.wilcoxon`, `alternative="greater"`). Apply Holm correction at alpha 0.05 and report a 95% interval of the mean paired difference and wins out of ten. The owner approves this use of `scipy.stats` specifically. `raw_exact` is descriptive.
4. Tabulate is approved for reporting.
5. Follow the Phase 3 prompt for metric edge cases. Fragmentation is NaN if no entity has at least two records.
6. Move the 26 legacy result files to `results/rq1_legacy/` and write `MANIFEST.csv` with filename, size and SHA-256 before moving them. Verify the archive afterward. Keep the legacy generated inputs in their original locations until Phase 8. The raw shipment CSV is the input to base preparation. The new RQ1 generated data lives under `data/generated/prepared/`, `splits/` and `noisy/`.
7. Use new files for implementation in Phases 1–7, with the specified exceptions for `backend/requirements.txt` and additive functions in `src/common/experiment_metadata.py`. Replace the audit's move and in-place refactor proposals with new modules in the prescribed locations, reusing legacy logic where applicable. Defer RQ2 delegation to shared code until Phase 8.
8. Add the future q-gram tests to `tests/common/test_encoding_qgrams.py`. Preserve the existing `tests/common/test_qgrams.py`.
9. Use Candidate B for `entity_id`. Group by molecule/test type, dosage, dosage form and per-pack unit count. For the key, case-fold Unicode, collapse whitespace and preserve punctuation. Represent missing dosage as an empty component and pack size as the decimal string of the parsed integer. Assign stable IDs in sorted tuple order. Preserve the source text in the prepared data.
10. Phase 4.5 confirmed the method set for RQ1 as `raw_exact`, `normalized_exact`, and pure `bloom_fuzzy`. Exclude hybrid or blocked variants.
11. Composite remains the pre-specified primary field set and description remains the ablation. In the validation-only Phase 4.5 diagnostic, their shared-threshold mean F1 values were 0.9172 and 0.9175, respectively. The owner judged the difference immaterial.
12. Keep connected components as the fuzzy clustering rule and the validation threshold grid at 0.60–0.99 inclusive in 0.01 steps.

## Phase 1 complete

The first action after reading the context and audit was to archive the 26 legacy files. `results/rq1_legacy/MANIFEST.csv` records archive-relative paths, byte sizes and SHA-256 digests. All entries matched after the moves. The archive follows the existing Git ignore rule for results. The legacy inputs at the root of `data/generated/` stayed in place.

### Files

- Configuration files `configs/base.yaml` and `configs/rq1.yaml`.
- Shared modules `src/common/config.py`, `paths.py`, `seeding.py`, and `src/common/data/schema.py`, `loader.py`, `preparation.py` and `splitting.py`.
- CLI module `experiments/rq1/prepare_rq1_data.py` with `base` and `split` stages.
- Tests under `tests/common/` in `test_config.py`, `test_paths.py`, `test_seeding.py`, `test_schema.py`, `test_loader.py`, `test_preparation.py` and `test_splitting.py`.
- PyYAML and SciPy are now direct dependencies in `backend/requirements.txt`.
- Generated `data/generated/prepared/base_dataset.csv`, `data/generated/prepared/entity_map.csv` and `data/generated/splits/split_seed0.json` through `split_seed9.json`.

Preparation assigns sequential record IDs before applying the cap or optional entity sampling when the configured `record_id` is absent. Entity IDs are also assigned before those steps. The base CSV preserves the description, dosage, dosage form and pack values from each retained source row. The entity map records the canonical key components and retained record counts. The optional entity sample uses seed 0 by default and keeps whole capped entities. Validation uses the rounded entity count, with both splits nonempty when at least two entities are available.

### Verification

The base stage retained 1,855 of 10,324 raw records across 149 entities. The cap removed 8,469 rows from 68 entities. Empty description rows, exact duplicate rows and removals from optional entity sampling each counted zero. Each split contains 45 validation and 104 test entities.

| Seed | Validation rows | Test rows |
| ---: | ---: | ---: |
| 0 | 545 | 1,310 |
| 1 | 544 | 1,311 |
| 2 | 534 | 1,321 |
| 3 | 590 | 1,265 |
| 4 | 586 | 1,269 |
| 5 | 532 | 1,323 |
| 6 | 472 | 1,383 |
| 7 | 503 | 1,352 |
| 8 | 558 | 1,297 |
| 9 | 518 | 1,337 |

Both CLI stages ran from `backend/` using `PYTHONPATH=app` and `python -m experiments.rq1.prepare_rq1_data --stage base` or `--stage split`. The 12 generated files were byte-identical across two runs. Verification checked the saved labels, unchanged source fields, entity map counts and split coverage. The full pytest suite from `backend/` passed **112 tests**, including 26 new tests, with a fresh temporary directory outside the repository.

## Phase 2 complete

Added `src/common/noise/typo_noise.py` and `tests/common/test_typo_noise.py`. The requested Phase 1 integration changes add `--stage noise` to `experiments/rq1/prepare_rq1_data.py` and `load_noisy(seed, level)` with a shared path helper to `src/common/data/loader.py`. The legacy noise generator and helpers were preserved.

The noise stage draws exactly `round(level × n_records)` records without replacement from the base for each independent `make_rng(seed, f"noise_{level}")` stream. It draws one uniform edit count per selected record and applies that count separately to each configured field. Each edit chooses among valid kinds and positions. Digit characters and separators directly between digits, including the plus in a combined strength, are protected. The final value cannot revert to the original. Short, missing or uneditable fields are logged as skips. The CLI's actual rate is the fraction of records with a changed field, the mean is total applied edits divided by selected records, and the skipped count is the number of skipped fields.

Running `python -m experiments.rq1.prepare_rq1_data --stage noise` from `backend/` with `PYTHONPATH=app` produced 30 datasets and 30 logs under `data/generated/noisy/seed0/` through `seed9/`. The 0% loader returns the prepared base.

| Nominal level | Selected and changed per seed | Actual rate | Skipped fields per seed |
| ---: | ---: | ---: | ---: |
| 5% | 93 | 5.013% | 0 |
| 15% | 278 | 14.987% | 0 |
| 30% | 556 | 29.973% | 0 |

| Seed | Mean typos at 5% | Mean typos at 15% | Mean typos at 30% |
| ---: | ---: | ---: | ---: |
| 0 | 1.548 | 1.493 | 1.505 |
| 1 | 1.516 | 1.482 | 1.495 |
| 2 | 1.538 | 1.529 | 1.484 |
| 3 | 1.505 | 1.464 | 1.493 |
| 4 | 1.538 | 1.511 | 1.477 |
| 5 | 1.538 | 1.525 | 1.504 |
| 6 | 1.548 | 1.514 | 1.525 |
| 7 | 1.495 | 1.511 | 1.491 |
| 8 | 1.484 | 1.500 | 1.471 |
| 9 | 1.527 | 1.500 | 1.487 |

The full pytest suite from `backend/` passed **128 tests**, including 16 Phase 2 tests. All 60 CSVs were byte-identical across two runs. Verification confirmed exact selected counts, unchanged non-noise columns, unchanged digit sequences, and agreement between each log and its saved dataset.

## Phase 3 complete

Added `src/common/preprocessing/normalizer.py`, `field_builder.py`, `src/common/linking/base.py`, `exact.py`, and `src/common/evaluation/metrics.py`. Added `tests/common/test_normalizer.py`, `test_field_builder.py`, `test_exact.py`, and `test_metrics.py`.

Normalization uses Unicode NFKC, case folding and letter/digit filtering. It stabilizes the result when removing a separator allows adjacent Unicode characters to compose. Field construction normalizes components separately when enabled, preserves the configured field order and keeps the composite `|` separators. Both exact baselines group by UTF-8 SHA-256 digest. The linker input excludes ground truth. The evaluator uses contingency counts and the owner’s edge conventions, rejects mismatched indexes or null labels, and averages fragmentation equally across repeated entities.

The full pytest suite from `backend/` passed **160 tests**, including 32 new cases. An inline sanity check used seed 0’s saved test split (1,310 records, 104 entities), the prepared control and the Phase 2 noisy files. The description and composite field sets produced identical label Series at every level for each method. No baseline script or result file was saved.

| Noise | Method | Precision | Recall | F1 | Fragmentation |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0% | raw_exact | 1.0000 | 0.9307 | 0.9641 | 1.1720 |
| 0% | normalized_exact | 1.0000 | 0.9307 | 0.9641 | 1.1720 |
| 5% | raw_exact | 1.0000 | 0.8389 | 0.9124 | 1.8710 |
| 5% | normalized_exact | 1.0000 | 0.8458 | 0.9164 | 1.8172 |
| 15% | raw_exact | 1.0000 | 0.6800 | 0.8095 | 3.2796 |
| 15% | normalized_exact | 1.0000 | 0.7028 | 0.8255 | 3.0645 |
| 30% | raw_exact | 1.0000 | 0.4712 | 0.6406 | 5.1183 |
| 30% | normalized_exact | 1.0000 | 0.5051 | 0.6712 | 4.7742 |

Recall fell at each higher noise level. The methods tied at 0%, and normalized exact recovered more matches at each positive level. Fifteen clean test entities had multiple raw descriptions, which accounts for the control’s remaining fragmentation. All predicted clusters in this split contained records from a single true entity, yielding precision of 1.0000.

| Noise | Selected test records | Identical after description normalization | Share |
| ---: | ---: | ---: | ---: |
| 0% | 0 | 0 | N/A |
| 5% | 65 | 5 | 7.69% |
| 15% | 198 | 21 | 10.61% |
| 30% | 376 | 33 | 8.78% |

## Phase 4 complete

Added `src/common/encoding/qgrams.py`, `bloom_filter.py`, `src/common/similarity/dice.py`, and `src/common/linking/clustering.py` and `bloom.py`. Added `tests/common/test_encoding_qgrams.py`, `test_bloom_filter.py`, `test_dice.py`, `test_clustering.py`, and `test_bloom.py`. The full pytest suite from `backend/` passed **193 tests**, including 33 Phase 4 cases.

Bloom encoding uses the configured key and caches each q-gram’s indexed HMAC positions per encoder. The transform hook receives each finished filter. RQ1 uses the default untransformed filters. Similarity visits upper-triangle blocks, using at least two blocks when a split has at least two records, and retains only qualifying pairs. Sparse connected components include isolated records. `prepare(df, tau_min)` supports repeated `labels_at(tau)` calls for thresholds at or above the cached minimum.

The inline sanity check used seed 0’s saved validation split (545 records, 45 entities) and a fixed fuzzy threshold of 0.80. Both exact baselines were recomputed on that split for every field set and noise level. Fuzzy recall was 1.0000 for all cases. Normalized exact reached 0.7981, 0.6422, and 0.4309 at 5%, 15%, and 30% noise, respectively.

At 0% noise, fuzzy precision was 0.6196 for description and 0.4318 for composite. Both produced a direct edge between lopinavir/ritonavir 200/50 mg and 100/25 mg, with Dice scores of 0.8451 and 0.8440 respectively. The largest clean description component contained three true entities and the largest clean composite component contained six. Composite precision and F1 were lower at every tested level, with equal recall. Fragmentation was 1.0000 for both fuzzy variants despite the cross-entity merges.

Across the eight fuzzy cases, linking took 0.2512–0.3711 seconds with a fresh q-gram cache per case. Separate memory runs measured 4.83–4.90 MiB peak traced allocation per fuzzy call, compared with 0.09–0.21 MiB for exact linking. The complete sanity process peaked at 98.25 MiB of working set, including imports and diagnostics. The threshold was fixed throughout. The sanity check wrote no script or result file.

## Phase 5 complete

Added `src/common/linking/threshold.py`, `src/common/experiment/runner.py` and `io.py`, and `experiments/rq1/rq1_methods.py` and `run_rq1.py`. Extended `src/common/experiment_metadata.py` with `write_metadata`. The existing metadata tests still pass. The new snapshot records the HMAC key fingerprint and omits the key.

Each seed reuses its saved entity split across noise levels. For each field set and noise level, tuning prepares Bloom similarities once on validation and records every grid score. It freezes the shared and per-noise cutoffs before scoring the test split. Linkers receive feature-only frames. `runtime_sec` measures the call to `link()`. The two exact baselines use `tau_mode=none` and a missing tau.

The full pytest suite from `backend/` passed **207 tests**, including 14 Phase 5 cases. The synthetic two-seed integration test ran all three preparation stages, verified the 64-row test schema and the selected thresholds, and confirmed repeatability apart from runtime and metadata timestamp. A separate test checks smoke output isolation.

Running `python -m experiments.rq1.run_rq1 --smoke` from `backend/` with `PYTHONPATH=app` wrote 32 test rows, 320 validation tuning rows and metadata under `results/rq1/smoke/`. The CLI reserves the dedicated smoke directory even when an output argument is supplied. Seed 0 used all 149 prepared entities because the count was below the smoke cap of 300. The held-out test split contained 1,310 records from 104 entities. The check verified the metadata omitted the key and the regular RQ1 output files were unchanged.

| Field set | Single tau | 0% tau | 5% tau | 15% tau | 30% tau |
| --- | ---: | ---: | ---: | ---: | ---: |
| Description | 0.92 | 0.99 (upper boundary) | 0.92 | 0.92 | 0.92 |
| Composite | 0.93 | 0.96 | 0.93 | 0.93 | 0.93 |

On the primary composite field set, single-tau fuzzy test F1 was 0.9079, 0.8993, 0.8899 and 0.8783 at the four levels. Normalized exact scored 0.9641, 0.9164, 0.8255 and 0.6712 on the same records. These scores are from the seed 0 smoke run.

## Phase 6 complete

Added `src/common/evaluation/aggregation.py`, `src/common/reporting/tables.py` and `figures.py`, and `experiments/rq1/build_rq1_report.py`. Added `tests/common/test_aggregation.py`, `test_tables.py`, `test_figures.py`, and `tests/rq1/test_rq1_report.py`. The full pytest suite from `backend/` passed **218 tests**, including 11 Phase 6 cases. Matplotlib and tabulate were already declared in `backend/requirements.txt`.

The report reads only test scores for performance and uses validation tuning rows to reconstruct the chosen thresholds. Its primary view uses composite fields and the single fuzzy threshold, with the description ablation and per-noise sensitivity in dedicated tables. Seed pairing uses the seed, noise level and field set keys. The normalized-exact comparison uses a one-sided exact Wilcoxon test with Holm adjustment over 5%, 15%, and 30% noise. Tied nonzero absolute differences use exhaustive sign permutations, as described in the [SciPy Wilcoxon documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html). Raw exact has descriptive paired differences and t intervals. A single seed leaves sample SD and t intervals unavailable, displayed as an en dash.

The smoke report was generated from `backend/app/` with the repository module paths on `PYTHONPATH`, using `python -m app.experiments.rq1.build_rq1_report --input results/rq1/smoke/raw_runs.csv --tau-input results/rq1/smoke/tau_selection.csv --out-dir results/rq1/smoke`. It produced five tables in CSV, Markdown and LaTeX, two 200 dpi PNGs, and `h1_check.md`. The Phase 5 smoke input files were verified unchanged.

On seed 0’s held-out test split, composite single-threshold fuzzy F1 was 0.8993, 0.8899, and 0.8783 at 5%, 15%, and 30% noise. It was below both exact baselines at 5% and above both at 15% and 30%. The 5% value was below 0.90.

## Phase 7 complete

The frozen configuration used seeds 0–9, noise levels 0%, 5%, 15%, and 30%, a 30/70 entity split, the 0.60–0.99 threshold grid in 0.01 steps, and Bloom parameters l=1024, k=4, q=2. The redacted preflight configuration was printed before the run. The seed 0 timing probe took 9.083 seconds. The full workflow took **99.693 seconds**, including 93.255 seconds for evaluation.

All 72 preparation files were regenerated in scratch storage and verified byte for byte against the saved inputs. The final run wrote 320 test rows, 3,200 validation tuning rows, metadata, five tables in three formats, two figures and the H1 note under `results/rq1/`. The existing 21 smoke files were checked by hash. The independent seed 0 replay matched 32 test rows after excluding runtime and reproduced all 320 tuning rows, the redacted config snapshot, and the HMAC fingerprint.

Added `experiments/rq1/validate_rq1_results.py` and `tests/rq1/test_validate_rq1_results.py`. Pytest from `backend/` passed **228 tests**. Validation printed **14 PASS, 1 WARN, 0 FAIL**. Sixteen F1 groups had sample SD above 0.05. The largest was 0.1832. Refer to [RQ1_RESULTS.md](RQ1_RESULTS.md) for the tables, figures, per-level H1 outcomes, and descriptive clean-pair profile.

### Sharing the implementation with RQ2 and RQ3

- Keep experiment-specific configuration in each RQ and reuse the shared config and purpose-based seeding, record schema, data loading, and experiment I/O and metadata helpers.
- Reuse the normalizer, field builder, padded q-grams, Bloom encoder, and blockwise Dice where their contracts match the later study. The encoder’s optional post-transform is the extension point for RQ2 or RQ3 privacy transforms. RQ1 continues to use the default untransformed filters.
- Reuse the linker protocol, connected components, and cluster contingency metrics where the later study evaluates record clusters. Retain separate metrics for RQ2’s existing two-party comparisons and for privacy-specific outcomes.
- Reuse runner, aggregation, table, and figure helpers for matching report requirements. Keep the RQ1 hypothesis comparison scoped to its owner-approved performance question.

## Phase 7b complete · Post-hoc analyses P1 and P2

This phase used the saved prepared and noisy inputs with all ten seeds. `src/common/linking/bloom_blocked.py` adds HMAC tokens for normalized dosage, dosage form and pack size. It reuses `PreparedBloom`, blockwise Dice and connected components on normalized descriptions within each block. The original linkers and `threshold.py` are unchanged. `experiments/rq1/posthoc.py` adapts the validation sweep for the blocked linker because the existing sweep constructs the pure Bloom linker directly. It uses the unchanged `select_single_tau`, including its higher-cutoff tie rule.

The opt-in runner flags `--post-hoc p1` and `--post-hoc p2` default to 0.30 and 0.50 validation fractions, respectively. `--val-fraction` can state that choice explicitly, and `--out-dir` can select a subdirectory of `results/rq1_posthoc/`. P1 loads the saved 30/70 splits. P2 writes ten new split files under its own `splits/` output folder using the original split seed stream. The runner and report builder reject writes to a completed frozen `results/rq1/` tree. To replay the original experiment, direct both commands to a scratch destination.

Each analysis wrote 360 test rows and 4,800 validation tuning rows. The post-hoc tuning CSV adds `method` to distinguish pure and blocked sweeps. The raw run schema is unchanged, with `field_set=description` for blocked matching and the blocking columns listed in metadata. The report retains the original methods’ composite primary view, adds the blocked description results, and adjusts each fuzzy-to-cleaned-exact comparison across the three positive typo levels within each run.

From `backend/` with `PYTHONPATH=app`, run `python -m experiments.rq1.run_rq1 --post-hoc p1` or substitute `p2`. For each output directory, run `python -m experiments.rq1.build_rq1_report --input <directory>/raw_runs.csv --tau-input <directory>/tau_selection.csv --out-dir <directory>`. The directories are `app/results/rq1_posthoc/p1_blocked_split3070` and `app/results/rq1_posthoc/p2_split5050` from `backend/`. Each has run CSVs, metadata, three tables in CSV, Markdown and LaTeX, and two 200 dpi figures. P1 took 129.65 seconds for evaluation and 2.49 seconds for reporting. P2 took 138.09 and 1.81 seconds, respectively.

Added `tests/rq1/test_rq1_posthoc.py`. Pytest from `backend/` passed 233 tests. All 42 frozen files, including smoke files, matched their before-and-after SHA-256 hashes. In P1, 320 original method test rows matched exactly after excluding runtime and all 3,200 original validation rows matched exactly. See the post-hoc section of [RQ1_RESULTS.md](RQ1_RESULTS.md) for outcomes and limitations.
