# Common-core refactor plan

Recon completed against the clean checkout at `eed1ccd` on `sarvi-component1`. Implementation proceeds on `component-1-refactor/common-core`. The owner selected final RQ1 acceptance goldens and a historical RQ2 snapshot.

## Repository tree

```text
RP-Component1/
  backend/
    requirements.txt
    app/
      main.py
      configs/{base,rq1}.yaml
      data/
        raw/
        generated/{prepared,splits,noisy}/
        generated/noisy_products_*_seed*.csv
      experiments/
        rq1/             # final run_rq1 plus legacy grid/noise drivers
        rq2/             # privacy grid, profiler, analyzer, DP ablation
      src/
        application_config.py
        common/
          {data,encoding,evaluation,experiment,linking,noise,preprocessing,reporting,similarity}/
          config.py, seeding.py, paths.py and legacy helpers
        rq1/             # legacy linkage and data services
        rq2/             # privacy, DP and application services
      tests/{common,rq1,rq2}/
  blockchain/{contracts,scripts,test}/
  docs/
  frontend/
  pytest.ini
```

## Encoding used by the final RQ1

`experiments/rq1/run_rq1.py` uses `rq1_methods.build_bloom_linker` and `src/common/linking/bloom.py`. The primary composite configuration joins individually normalized description, dosage, form, and pack size with `|`, then encodes one bit vector per record. It uses padded distinct bigrams and indexed HMAC-SHA256 positions at l=1024 and k=4 with the configured fixed research key. Description-only is the field ablation. The final primary results have no separate deterministic dosage token.

## Migration map

Locations below are relative to `backend/app`. Shared implementation paths already in `src/common` should be reused.

| Current location | Shared destination | RQ1 users | RQ2 users | Differences and canonical RQ1 behavior |
| --- | --- | --- | --- | --- |
| `src/common/config.py`, `configs/{base,rq1}.yaml`, `src/rq2/{experiment_config,parameter_validation}.py`, `src/application_config.py` | Existing YAML loader and config types, new RQ2/RQ3 YAML profiles | Preparation, accuracy, reports | Grid, DP ablation, profiler, privacy pipeline | RQ1 uses YAML and tau 0.60?0.99 by 0.01. RQ2 uses Python defaults and tau 0.30?0.99 by 0.005. Existing RQ2 l=(2048,1024,512,256,128) and k=(2,4,8,15,30,50). Requested l=(1024,512,256), k=(2,4,10,30) and 15% are a new default sweep. Deployment settings have separate environment consumers. |
| `src/common/data/{preparation,loader,schema,splitting}.py`, `src/rq2/rq2_dataset.py` | Existing data preparation, schema, loader, and split modules | Accuracy and preparation | Grid, profiler, DP ablation | Final RQ1 keeps shipment-level record IDs and entity-group splits, with a 30% validation default. RQ2 aligns legacy files by record ID and uses sampled entity representatives, a 50/50 entity-index split, separate victim variants, and counts or weights. RQ1 is the source for identical record-pair evaluation. RQ2's population and sampling choices affect privacy estimates. |
| `src/common/noise/typo_noise.py`, `src/common/noise_injection.py`, `experiments/rq1/{prepare_rq1_data,noise_dataset_generator}.py`, `src/rq2/privacy_pipeline.py` | Existing `src/common/noise/` and common artifact loader | Final preparation and legacy generator | Controlled-file and inline scenarios | Final RQ1 selects round(p*n) records and applies 1?2 typos with numeric protection. Legacy RQ1 and inline RQ2 apply a length-proportional number of edits per eligible string with different RNGs. The legacy CLI owns `--all-fields`. Preserve the flag through the final preparation implementation only after agreeing how its output is versioned. |
| `src/rq2/text_normalizer.py`, `src/rq2/rq2_dataset.py`, `src/common/preprocessing/` | Existing `normalizer.py` and `field_builder.py` | Exact and Bloom linkers | Dataset loader and scenario | RQ1 uses NFKC, casefolding, Unicode letters/digits, missing-to-empty, and explicit composite separators. RQ2 uses NFKD, lowercasing and ASCII regex cleanup which removes field separators. |
| `src/rq2/qgram_utils.py`, `src/common/encoding/qgrams.py`, `src/common/qgram_extractor.py` | Existing `encoding/qgrams.py` | Bloom encoder | Encoder, profiler, scenario | RQ1 pads with underscores and uses distinct complete windows. RQ2 defaults to unpadded windows and emits a short nonempty string as a gram. The RQ1 encoder bypasses q-gram extraction for empty text. Application field-tagging helpers have separate callers. |
| `src/rq2/bloom_encoder.py`, `src/common/encoding/bloom_filter.py`, `src/common/keyed_bloom_filter.py` | Existing `encoding/bloom_filter.py` for the research pipelines | Composite and description Bloom linkers | Utility and privacy encodings, q-gram positions, DP ablation | Final RQ1 hashes each counter-prefixed gram independently with a fixed key. RQ2 derives a seed key and double-hashes with a coprime step. The application's bitarray encoder has a separate serving contract. Extend the RQ1 encoder for arbitrary positive l, fill ratio, and read-only access to the same gram positions when authorized. |
| `src/rq2/similarity_matching.py`, `src/common/similarity/dice.py`, `src/rq1/dice_similarity.py` | Existing `similarity/dice.py` | RQ1 unordered scores and legacy resolver | A?B matrices for utility and privacy | NumPy Dice already implements the same binary-vector formula and zero-denominator result. RQ1 uses float64 sums and a separate unordered pair spool. Keep cross-matrix scoring available. |
| `src/rq2/similarity_matching.py`, `src/common/linking/{bloom,clustering,threshold}.py`, `src/rq1/entity_resolver.py` | Existing linking and threshold modules | Final threshold selection, connected components and canonical labels | Threshold sweeps and cross-party matching | Final RQ1 uses unordered edges and takes transitive closure. It chooses the highest tau maximizing mean validation F1 across levels, with per-level selection as an ablation. RQ2 makes direct A?B matches with 1e-12 slack and also selects thresholds with FPR constraints of 1% and 5%. Legacy serving resolver uses a streaming representative. |
| `src/rq2/privacy_pipeline.py` (`run_exact`), `src/rq2/similarity_matching.py`, `src/common/linking/exact.py`, `src/rq1/exact_matcher.py` | Existing `linking/exact.py` | Raw and normalized SHA-256 grouping | HMAC baseline and privacy comparator | RQ1's published exact baselines use plain SHA-256 over raw/normalized field strings. RQ2 uses keyed HMAC-SHA256 and counts cross-party token matches. Preserve the published RQ1 variants and identify any keyed comparator explicitly. |
| `src/rq2/similarity_matching.py`, `src/common/evaluation/metrics.py`, `src/rq1/record_linkage_metrics.py` | Existing `evaluation/metrics.py` | Contingency pairs and fragmentation | Direct precision/recall/F1/FPR | RQ1's ground truth is all unordered within-entity pairs. RQ2 truth is the A?B diagonal. RQ1's empty/empty scores are 1, RQ2's are 0. Share count-based arithmetic only with explicit handling of those conventions. |
| `experiments/rq2/results_analyzer.py`, `src/common/evaluation/aggregation.py` | Existing shared aggregation plus generic effect-size helpers as warranted | Paired reporting | Paired privacy hypotheses and Holm correction | RQ1 tests one-sided differences and uses t intervals. RQ2 applies two-sided tests, bootstraps paired effects, and defines different Holm families. Reuse generic adjustment and retain each hypothesis policy. |
| `src/common/{experiment_metadata,paths,seeding}.py`, `src/common/experiment/`, `experiments/rq2/grid_runner.py` | Existing shared experiment, paths, and seeding packages | Grid, validated I/O, metadata and plots | Pool scheduling, sidecars, CSV load/write and plots | RQ1 has named RNG streams and stable record IDs. RQ2 derives streams with ordered SeedSequence components and uses separate attack/DP seeds. Reuse common interfaces while retaining existing RNG inputs for any baseline that must replay. Column contracts are artifact-specific. |
| `src/rq2/numpy_randomized_response.py`, `experiments/rq2/dp_ablation_runner.py`, `src/rq2/bitarray_differential_privacy.py` | RQ3 driver and shared NumPy transform when needed by both studies | No DP in frozen runs | DP ablation and serving integration | No separate RQ3 package currently exists. The experiment's NumPy transform and the serving bitarray API have distinct callers. |
| `src/rq2/{harmonization_pipeline,blockchain_client}.py`, `src/rq1/entity_resolver.py` | Shared serving modules if moving these application callers is in scope | Legacy streaming linkage | App and ledger integration | `harmonization_pipeline` imports RQ1's legacy resolver. This cross-import belongs to the serving path. Regression coverage must protect the public API and ledger behavior if moved. |
| `src/rq2/{privacy_attacks,privacy_metrics}.py` | Remain experiment-specific except generic fill calculation | None | Privacy experiment | If the canonical encoding migration is approved, privacy receives the composite RQ1 vector. There is no standalone dosage token to report for this design. |

## Equivalence decision

At the same key, l=1024, k=4, and q-gram `ab`, indexed RQ1 HMAC produces positions 233, 682, 794, 1018. RQ2 double hashing produces 284, 575, 866, 1017. Under each profile's padding policy, Dice for `ab` versus `ac` is 1/3 for RQ1 and 0 for RQ2 in this diagnostic. A single threshold of 0.3 produces different decisions.

The compatible regression target for the shared encoder is final RQ1 on the same records, field set, key, tau, and pair definition. The current RQ2 snapshot can document historical results, but its Bloom and linkage artifacts cannot be acceptance goldens for a migration to RQ1's semantics. Keeping legacy RQ2 numerically identical would require retaining its encoding and experiment policies and relaxing the single-encoding requirement.

## Proposed behaviour changes (not applied)

- Adopt the canonical RQ1 dataset artifacts and RQ1 encoding in RQ2. Decide whether RQ2's original cross-party utility remains a separately reported metric alongside an exact RQ1 parity check.
- Switch RQ2's default sweep to the requested l/k values and one 15% noise level. Remove inline typo generation and retain the preparation flag for all-field corruption.
- Relax the power-of-two restriction while retaining the existing RQ1 encoding formula. Decide the common k>l validation policy, since the final RQ1 encoder currently permits it and RQ2 rejects it.
- Move the existing DP study into a separately named RQ3 entry point and preserve existing callers where needed.

## Verification sequence after authorization

1. On the approved branch, capture both original profiles on fixed subsets of no more than 200 records, with four noise levels, fixed seeds, and RQ2 at 1024/4. Fix record selection and row alignment before capturing output. Save noisy inputs, filter hashes, pair IDs and Dice scores, direct decisions, cluster-implied decisions where applicable, and precision/recall/F1. Keep validation separate from test data.
2. Run the regression after each shared-module change. Compare exact values by type and scores with absolute tolerance 1e-9. Delay removing code until its replacement is verified. Commit each completed phase separately.
3. Add AST checks for experiment-layer cross-imports and shared definitions. Verify published RQ1 artifacts, record-pair invariants, entry points, and the full configured pytest suite. Existing requirements already declare tabulate, PyYAML and SciPy.
4. Write the final report with verified test output, moved/deleted modules, and explicitly approved result changes.

## Static module and function inventory

The inventory follows local imports from RQ1 and RQ2 and includes both final experiment drivers and legacy modules in those namespaces. Names include module functions and class methods. Imports are source references, with no runtime paths exercised.

| Module | Reachable from | Functions and classes |
| --- | --- | --- |
| `experiments/rq1/build_rq1_report.py` | RQ1 | `_number`, `_score`, `_primary_summary`, `_f1_table`, `_fragmentation_table`, `_ablation_table`, `_tau_sensitivity`, `_paired_table`, `_h1_note`, `build_report`, `main` |
| `experiments/rq1/grid_runner.py` | RQ1 | `Experiment1AccuracyBenchmark`, `Experiment1AccuracyBenchmark.__init__`, `Experiment1AccuracyBenchmark._result_name`, `Experiment1AccuracyBenchmark._noise_axis_label`, `Experiment1AccuracyBenchmark._load_base_dataset`, `Experiment1AccuracyBenchmark._load_clean`, `Experiment1AccuracyBenchmark._inject_noise`, `Experiment1AccuracyBenchmark._load_noisy_all_records`, `Experiment1AccuracyBenchmark._get_dataset`, `Experiment1AccuracyBenchmark._run_exact`, `Experiment1AccuracyBenchmark._encode_records`, `Experiment1AccuracyBenchmark._run_resolver`, `Experiment1AccuracyBenchmark._row`, `Experiment1AccuracyBenchmark.execute_benchmark`, `Experiment1AccuracyBenchmark.select_threshold`, `Experiment1AccuracyBenchmark.select_threshold_per_noise`, `Experiment1AccuracyBenchmark.save_tau_policies`, `Experiment1AccuracyBenchmark.statistical_comparison`, `Experiment1AccuracyBenchmark.entity_bootstrap_comparison`, `Experiment1AccuracyBenchmark.aggregate`, `Experiment1AccuracyBenchmark._bf_policy_rows`, `Experiment1AccuracyBenchmark._headline_long`, `Experiment1AccuracyBenchmark._fmt`, `Experiment1AccuracyBenchmark._latex_fix`, `Experiment1AccuracyBenchmark.headline_table`, `Experiment1AccuracyBenchmark.oracle_threshold_table`, `Experiment1AccuracyBenchmark._style_for`, `Experiment1AccuracyBenchmark.plot_headline`, `Experiment1AccuracyBenchmark.plot_threshold_sensitivity`, `main` |
| `experiments/rq1/noise_dataset_generator.py` | RQ1 | `SyntheticNoiseGenerator`, `SyntheticNoiseGenerator.__init__`, `SyntheticNoiseGenerator._inject_typo`, `SyntheticNoiseGenerator.generate_noisy_datasets` |
| `experiments/rq1/posthoc.py` | RQ1 | `protect_frozen_results`, `post_hoc_destination`, `tune_blocked_tau` |
| `experiments/rq1/prepare_rq1_data.py` | RQ1 | `_prepare_base`, `_prepare_splits`, `_prepare_noise`, `main` |
| `experiments/rq1/rq1_methods.py` | RQ1 | `build_exact_linkers`, `build_bloom_linker` |
| `experiments/rq1/run_rq1.py` | RQ1 | `_thresholds`, `_destination`, `_sample_for_smoke`, `_evaluate_test`, `_record_test`, `run_experiment`, `_parse_noise_level`, `main` |
| `experiments/rq1/validate_rq1_results.py` | RQ1 | `_dtypes`, `_scores_in_range`, `_expected_runs`, `_matches_validation`, `validate_results`, `main` |
| `experiments/rq2/dataset_profiler.py` | RQ2 | `main` |
| `experiments/rq2/dp_ablation_runner.py` | RQ2 | `main` |
| `experiments/rq2/grid_runner.py` | RQ2 | `work`, `print_entity_weights`, `main` |
| `experiments/rq2/results_analyzer.py` | RQ2 | `ci95`, `aggregate`, `heatmap`, `pareto_front`, `holm_bonferroni`, `paired_effect`, `merge_paired`, `load_run_meta`, `validate_run_metas`, `main` |
| `src/application_config.py` | RQ1, RQ2 | `ExperimentConfig`, `Config`, `Config.ensure_directories` |
| `src/common/config.py` | RQ1 | `PathsConfig`, `ColumnsConfig`, `ColumnsConfig.text`, `RawColumnsConfig`, `BloomConfig`, `TauGridConfig`, `Config`, `_read_yaml`, `_merge`, `_validate_names`, `_validate`, `load_config` |
| `src/common/data/loader.py` | RQ1 | `_read_csv`, `read_raw_csv`, `read_prepared_csv`, `read_noisy_csv`, `noisy_csv_path`, `load_noisy` |
| `src/common/data/preparation.py` | RQ1 | `PreparationResult`, `_text_key`, `_pack_key`, `_entity_key`, `_source_columns`, `prepare_base_data`, `prepare_base_dataset` |
| `src/common/data/schema.py` | RQ1 | `required_columns`, `validate_frame` |
| `src/common/data/splitting.py` | RQ1 | `split_entities`, `_check_split`, `apply_split`, `save_split`, `load_split` |
| `src/common/encoding/bloom_filter.py` | RQ1 | `BloomFilterEncoder`, `BloomFilterEncoder.__init__`, `BloomFilterEncoder._positions`, `BloomFilterEncoder.encode`, `BloomFilterEncoder.encode_many` |
| `src/common/encoding/qgrams.py` | RQ1 | `validate_qgram_parameters`, `extract_qgrams` |
| `src/common/evaluation/aggregation.py` | RQ1 | `aggregate_runs`, `holm_adjust`, `_select`, `_wilcoxon_greater`, `paired_difference` |
| `src/common/evaluation/metrics.py` | RQ1 | `_count_pairs`, `evaluate_clusters` |
| `src/common/experiment/io.py` | RQ1 | `write_csv`, `read_csv` |
| `src/common/experiment/runner.py` | RQ1 | `iter_grid`, `RunRecorder`, `RunRecorder.__init__`, `RunRecorder.add`, `RunRecorder.to_frame`, `timed` |
| `src/common/experiment_metadata.py` | RQ1, RQ2 | `add_common_args`, `parse_standard`, `data_fingerprint`, `package_versions`, `config_metadata`, `write_run_csv`, `write_markdown`, `write_metadata` |
| `src/common/keyed_bloom_filter.py` | RQ1, RQ2 | `KeyedBloomFilter`, `KeyedBloomFilter.__init__`, `KeyedBloomFilter._hash_position`, `KeyedBloomFilter.encode`, `KeyedBloomFilter.calculate_bit_density`, `KeyedBloomFilter.to_bytes`, `KeyedBloomFilter.to_hex`, `KeyedBloomFilter.from_bytes`, `KeyedBloomFilter.from_hex` |
| `src/common/linking/base.py` | RQ1 | `Linker`, `Linker.link` |
| `src/common/linking/bloom.py` | RQ1 | `PreparedBloom`, `PreparedBloom.labels_at`, `BloomLinker`, `BloomLinker.__init__`, `BloomLinker.prepare`, `BloomLinker.link` |
| `src/common/linking/bloom_blocked.py` | RQ1 | `blocking_fields`, `blocking_token`, `BloomBlockedLinker`, `BloomBlockedLinker.__init__`, `BloomBlockedLinker.prepare`, `BloomBlockedLinker.link` |
| `src/common/linking/clustering.py` | RQ1 | `labels_from_pairs` |
| `src/common/linking/exact.py` | RQ1 | `sha256_hex`, `ExactLinker`, `ExactLinker.__init__`, `ExactLinker.link` |
| `src/common/linking/threshold.py` | RQ1 | `BloomLinkerArgs`, `tune_tau`, `select_single_tau`, `select_per_noise_tau` |
| `src/common/noise/typo_noise.py` | RQ1 | `_protected`, `_positions`, `_candidate`, `_choose_typo`, `apply_typo`, `_mutate_field`, `inject_noise` |
| `src/common/noise_injection.py` | RQ1, RQ2 | `NoiseSpec`, `NoiseSpec.__post_init__`, `mutate_once`, `add_typos`, `add_noise`, `levenshtein`, `inject_typo` |
| `src/common/paths.py` | RQ1 | `app_dir`, `_directory`, `raw_dir`, `raw_csv_path`, `prepared_dir`, `splits_dir`, `noisy_dir`, `results_dir` |
| `src/common/preprocessing/field_builder.py` | RQ1 | `build_field_strings` |
| `src/common/preprocessing/normalizer.py` | RQ1 | `normalize`, `normalize_series` |
| `src/common/preprocessor.py` | RQ1, RQ2 | `TextPreprocessor`, `TextPreprocessor.normalize`, `TextPreprocessor.extract_qgrams`, `TextPreprocessor.extract_token_qgrams`, `TextPreprocessor.extract_token_qgrams_list`, `TextPreprocessor.parse_attributes_from_text`, `TextPreprocessor.extract_composite_qgrams`, `TextPreprocessor.compare_token_overlap` |
| `src/common/qgram_extractor.py` | RQ1, RQ2 | `QGramExtractor`, `QGramExtractor.__init__`, `QGramExtractor.pad_token`, `QGramExtractor.extract_from_token`, `QGramExtractor.extract_token_qgrams`, `QGramExtractor.extract_token_qgrams_list`, `QGramExtractor.extract_global_qgrams`, `QGramExtractor.extract_composite_qgrams`, `QGramExtractor.compare_token_overlap` |
| `src/common/reporting/figures.py` | RQ1 | `_series`, `_error_bars`, `_finish`, `line_chart`, `grouped_bar_chart` |
| `src/common/reporting/tables.py` | RQ1 | `format_mean_std`, `save_table` |
| `src/common/seeding.py` | RQ1 | `make_rng` |
| `src/common/similarity/dice.py` | RQ1 | `_dice_block`, `dice_matrix`, `dice_pair`, `compute_similar_pairs` |
| `src/rq1/cross_org_simulator.py` | RQ1 | `CrossOrgSimulator`, `CrossOrgSimulator.__init__`, `CrossOrgSimulator._simulate_org_a`, `CrossOrgSimulator._simulate_org_b`, `CrossOrgSimulator._simulate_org_c`, `CrossOrgSimulator.generate_cross_org_dataset` |
| `src/rq1/dice_similarity.py` | RQ1, RQ2 | `DiceSimilarityEngine`, `DiceSimilarityEngine.calculate_dice`, `DiceSimilarityEngine.calculate_jaccard`, `DiceSimilarityEngine.find_best_candidate` |
| `src/rq1/entity_resolver.py` | RQ1, RQ2 | `ClusterEntity`, `ClusterEntity.__init__`, `ClusterEntity.add_member`, `EntityResolver`, `EntityResolver.__init__`, `EntityResolver.get_candidate_filters`, `EntityResolver.resolve_record`, `EntityResolver.process_dataset`, `EntityResolver.reset` |
| `src/rq1/exact_matcher.py` | RQ1 | `ExactMatcher`, `ExactMatcher.__init__`, `ExactMatcher.compute_hash`, `ExactMatcher.resolve_record`, `ExactMatcher.process_dataset`, `ExactMatcher.reset` |
| `src/rq1/record_linkage_metrics.py` | RQ1 | `LinkageMetrics`, `LinkageMetrics.compute_pairwise_metrics`, `LinkageMetrics.format_metrics_table`, `LinkageMetrics.entity_bootstrap_ci` |
| `src/rq1/shipment_data_loader.py` | RQ1 | `SupplyChainDataLoader`, `SupplyChainDataLoader.__init__`, `SupplyChainDataLoader._locate_raw_file`, `SupplyChainDataLoader.basic_clean_text`, `SupplyChainDataLoader.load_raw_dataset`, `SupplyChainDataLoader.extract_clean_master`, `SupplyChainDataLoader.generate_ground_truth_pairs`, `SupplyChainDataLoader.run` |
| `src/rq2/__init__.py` | RQ2 | Constants or imports |
| `src/rq2/bitarray_differential_privacy.py` | RQ2 | `LocalDifferentialPrivacy`, `LocalDifferentialPrivacy.calculate_flip_probability`, `LocalDifferentialPrivacy.apply_randomized_response`, `LocalDifferentialPrivacy.batch_apply_ldp`, `LocalDifferentialPrivacy.verify_empirical_flip_rate` |
| `src/rq2/blockchain_client.py` | RQ2 | `BlockchainClient`, `BlockchainClient.__init__`, `BlockchainClient._initialize_connection`, `BlockchainClient._to_bytes32`, `BlockchainClient.retrieve_stored_candidates`, `BlockchainClient._get_fee_fields`, `BlockchainClient.commit_harmonized_record`, `BlockchainClient.verify_record_exists`, `BlockchainClient.get_record`, `BlockchainClient.reset_mock_state`, `BlockchainClient.get_ledger_summary` |
| `src/rq2/bloom_encoder.py` | RQ2 | `_is_pow2`, `BloomEncoder`, `BloomEncoder.__init__`, `BloomEncoder._hashes`, `BloomEncoder.gram_positions`, `BloomEncoder.encode_many`, `BloomEncoder.encode` |
| `src/rq2/experiment_config.py` | RQ2 | Constants or imports |
| `src/rq2/harmonization_pipeline.py` | RQ2 | `HarmonizationPipeline`, `HarmonizationPipeline.__init__`, `HarmonizationPipeline.synchronize_with_ledger`, `HarmonizationPipeline.process_single_record`, `HarmonizationPipeline.process_batch`, `HarmonizationPipeline.reset` |
| `src/rq2/numpy_randomized_response.py` | RQ2 | `flip_probability`, `randomized_response` |
| `src/rq2/parameter_validation.py` | RQ2 | `validate_tau`, `validate_bloom_parameters`, `validate_eps`, `validate_noise`, `validate_overlap`, `validate_n_records`, `validate_bit_top`, `validate_dataset`, `validate_dictionary` |
| `src/rq2/privacy_attacks.py` | RQ2 | `reid_attack`, `exact_reid_attack`, `frequency_attack`, `bit_qgram_attack` |
| `src/rq2/privacy_metrics.py` | RQ2 | `fill_stats`, `bit_entropy`, `collision_load`, `expected_fill`, `effective_noise` |
| `src/rq2/privacy_pipeline.py` | RQ2 | `Scenario`, `build_scenario`, `_tokens`, `_base_row`, `run_bloom`, `run_exact` |
| `src/rq2/qgram_utils.py` | RQ2 | `qgrams`, `qgram_set` |
| `src/rq2/results_schema.py` | RQ2 | `SchemaError`, `SchemaError.__str__`, `validate_results` |
| `src/rq2/rq2_dataset.py` | RQ2 | `Dataset`, `Dataset.n`, `_zipf_weights`, `synthetic_dataset`, `resolve_columns`, `csv_dataset`, `load_dataset`, `controlled_noise_dataset`, `apply_real_frequency_counts` |
| `src/rq2/similarity_matching.py` | RQ2 | `dice_matrix`, `_prf`, `sweep`, `tune_tau_full`, `tune_tau`, `metrics_at`, `auc_and_separation`, `exact_metrics` |
| `src/rq2/text_normalizer.py` | RQ2 | `normalize` |

