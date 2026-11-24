# Serving alignment plan

Recon starts from `108c8b4` on `component-1-refactor/common-core`.

## Serving call graph and persistence

| Location | Entry points and data |
| --- | --- |
| `backend/app/main.py` | `HarmonizeRequest`, `HarmonizeResponse`, `get_pipeline`, `harmonize`, `health`, `ledger_summary`. The API accepts four fields and exposes the predicted cluster and ledger status. |
| `frontend/src/main.jsx` | `App`, `updateField`, `submit`, and `loadStatus` submit unencoded records and render the returned cluster/status. The form currently sends description without separate dosage, form or pack inputs. |
| `src/rq2/harmonization_pipeline.py` | `HarmonizationPipeline.__init__`, `process_single_record`, `process_batch`, `synchronize_with_ledger`, `reset`. Builds input fields, encodes and optionally perturbs vectors, compares leaders, and hashes the record ID, raw description and organization for the ledger. APIs and demos instantiate this class. |
| `src/application_config.py`, `.env.example` | `Config` loads environment settings, including the legacy key/default parameters, contract address, RPC and mock policy. The encoder also has its own legacy fallback. |
| `src/common/preprocessor.py`, `qgram_extractor.py`, `keyed_bloom_filter.py` | `TextPreprocessor.normalize`, `parse_attributes_from_text`, `extract_composite_qgrams`, token/global extraction and token overlap. `QGramExtractor` owns token padding, tagged composite generation and overlap. `KeyedBloomFilter.__init__`, `_hash_position`, `encode`, density and `to_bytes`/`from_bytes`/`to_hex` handle the previous bit layout. The historical RQ1 grid and existing frozen tests still import these modules. |
| `src/rq1/entity_resolver.py`, `dice_similarity.py` | `EntityResolver.resolve_record`, `get_candidate_filters`, `process_dataset`, `reset`, and `ClusterEntity.add_member` maintain immutable first-member representatives. `DiceSimilarityEngine.find_best_candidate` and `calculate_dice` select the best leader. Jaccard is a legacy helper. |
| `src/rq2/bitarray_differential_privacy.py` | `LocalDifferentialPrivacy.calculate_flip_probability`, `apply_randomized_response`, `batch_apply_ldp`, and `verify_empirical_flip_rate` cover optional randomized response to serving bit arrays. |
| `src/rq2/blockchain_client.py` | `__init__` and `_initialize_connection` check chain, ABI, contract code, and Bloom byte width. `retrieve_stored_candidates`, `commit_harmonized_record`, `get_record`, `verify_record_exists`, `get_ledger_summary`, and `reset_mock_state` deal with real or mock state. `_to_bytes32` checks record hashes, and `_get_fee_fields` prepares transaction fees. |
| `blockchain/contracts/HarmonizedSupplyChain.sol`, `blockchain/scripts/deploy.js` | Constructor receives the configured byte width. `storeHarmonizedRecord` validates width and unique IDs/hashes, stores opaque bytes, and preserves the first leader per cluster string. `getClusterLeaders`, `getCandidateRecords`, and `getRecord` return stored bytes and identifiers. |
| `blockchain/test/` | API health/harmonization, off-chain matching and rejection of empty descriptions, Bloom serialization/empty filter, preprocessing boundaries, Dice mismatch and similarity, streaming leader membership, optional DP, Web3 hash validation/mock policy/gas, and Solidity storage/leader/duplicate tests. Some Python files import obsolete module paths. |
| `backend/app/tests/` | Golden and common tests cover canonical RQ1 encoding and the historical compatibility interfaces. In particular, `common/test_qgrams.py` explicitly asserts legacy token boundaries, normalization and missing dosage tags. Preserve those historical imports and assertions while severing their serving callers. |

Paths beginning with `src/` above are relative to `backend/app/`.

The former preprocessing surface includes `extract_qgrams`, `extract_token_qgrams`, `extract_token_qgrams_list`, and `compare_token_overlap` on `TextPreprocessor`. The legacy `QGramExtractor` also exposes `pad_token`, `extract_from_token`, `extract_global_qgrams`, the token/set and list extractors, the composite extractor, and overlap. The encoder's remaining utilities were `from_hex` and `calculate_bit_density`. Its historical clients outside the serving path include `experiments/rq1/grid_runner.py`, `src/rq1/exact_matcher.py`, and `src/rq1/shipment_data_loader.py`.

The pre-change Python test inventory is `test_api.py` (health and harmonization), `test_end_to_end.py` (matching and empty input), `test_bloom_filter.py` (round-trip and empty bits), `test_preprocessor.py` (normalization and tagged fields), `test_similarity.py` (identical, disjoint, and width mismatch), `test_entity_resolver.py` (leaders and new clusters), `test_differential_privacy.py` (probability, reproducibility, and no-op behavior), and `test_blockchain_client.py` (hash formatting, mock opt-in, and gas accounting). `HarmonizedSupplyChain.js` tests authorization, width and duplicate validation, and owner pause controls. It deploys an isolated instance from a test fixture.

## Encoding comparison

| Property | Previous serving | Canonical research |
| --- | --- | --- |
| Tokenization | Field-tagged, per-token windows | One composite string joined with `|` |
| Fields | Name, dosage, form, pack with parsing, tags and missing-value markers | Individually normalized description, dosage, form and pack in that order, with empty missing values |
| Normalization | Legacy inventory-marker removal, case conversion and punctuation handling | NFKC, case folding and Unicode letters/digits |
| q and padding | Default q=3, underscore padding at each token | q=2, underscores at both ends of the complete string |
| HMAC input and digest | `qgram:index`, eight big-endian digest bytes | `index:qgram`, four big-endian digest bytes |
| Key | Environment with a fallback | Configured research key |
| l and k | Environment defaults 1024 and 4 | YAML defaults 1024 and 4 |
| Output | Big-endian bitarray packed to 128 bytes for the ledger | NumPy uint8 logical bits, packed at the serving boundary |
| Clustering | Best existing fixed representative above tau | Connected components of all qualifying edges |

## Existing state and migration

The contract depends on byte width and opaque identifiers. It does not compute or inspect q-grams, positions, keys or Dice, and its 128-byte format remains valid. There is no database containing serving filters in this path. Python mock and resolver state are in memory. Research golden data remains fixed. Previous on-chain filters and cluster assignments belong to the previous encoding and cannot be reconstructed from the bit vectors alone.

The contract already persists a cluster string alongside every vector. Use that field to persist the encoder version and a key namespace and require both when loading candidates. The API can still expose the local cluster ID. Legacy unversioned and foreign-namespace vectors must fail closed. For a disposable local Hardhat environment, use empty state, then re-encode and recommit from original descriptions and structured fields in serving order. Existing record IDs and hashes are unique, so replaying in place into the same populated contract is rejected. A retained deployment needs an approved migration to a separate empty ledger instance. No contract, deployment, or live ledger operation is part of this task.
