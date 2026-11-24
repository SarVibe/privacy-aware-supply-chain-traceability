# Serving alignment and RQ1 over-merging

Work is on `component-1-refactor/serving-alignment`, branched from `108c8b4`. The evaluated composite encoder now supplies the serving Bloom vectors. The online resolver still uses fixed first-member leaders. The frozen RQ1 and historical RQ2 snapshots and original data have an empty diff against the starting branch. The RQ1 alternatives run only through diagnostic commands.

## A0–A3. Serving changes

Serving loads `l=1024`, `k=4`, `q=2`, and padding from the RQ1 YAML, normalizes and joins the same four fields, and uses the same indexed HMAC-SHA256 positions. The serving cutoff is 0.80. Serving takes its UTF-8 encoder key from `SHARED_SECRET_KEY` and raises an error before connecting to the ledger when the key is missing. Research continues to use the configured research key. The existing optional serving randomized-response step still runs after encoding.

The API includes `encoder_version`. The identifier encodes the ordered composite and normalization revision, separator, q, padding character, HMAC input layout, digest prefix width, l, and k. Versioned vectors also carry a domain-separated key namespace. Streaming comparison rejects an incompatible vector before Dice. The blockchain client rejects unversioned or foreign-namespace candidates even when mock fallback is enabled. On chain, the existing cluster string stores `encoder_version/key_namespace/local_cluster_id`, and the API returns the local cluster ID. Packed Bloom vectors remain 128 bytes in the standard configuration.

The 200-record historical capture uses the fixed public test key and no DP. At a matched tau of 0.80, all 200 packed vector hashes changed, the streaming cluster count changed from 16 to 20, and predicted pairs changed from 2,822 to 2,025. Replaying the original commit in isolation at its previous serving default of 0.92 gives 20 clusters and 1,949 pairs. [Recon and format table](SERVING_ALIGNMENT_PLAN.md) · [Snapshot manifest](backend/app/tests/golden/serving_before/manifest.json) · [Per-record before/after results](outputs/diagnostics/serving_agreement/serving_before_after.csv)

### Files and retired serving paths

| Area | Changed files or responsibilities |
| --- | --- |
| Encoding | `backend/app/src/common/config.py`, `encoding/bloom_filter.py`, `encoding/versioned_bloom.py`, and `preprocessing/field_builder.py` contain shared assembly, HMAC layout, key loading, version metadata and wire packing. |
| Serving | `backend/app/main.py`, `src/rq2/harmonization_pipeline.py`, `src/rq2/blockchain_client.py`, and `src/rq1/entity_resolver.py` handle versioned requests, vectors and candidates. `src/rq1/dice_similarity.py` and `src/rq2/bitarray_differential_privacy.py` lost their retired legacy-encoding demos. `.env.example` clarifies the key and which defaults are historical. |
| Research diagnostics | `backend/app/configs/rq1_diagnostics.yaml`, `experiments/rq1/{diagnostic_inputs,serving_agreement,overmerge_diagnostics,tuned_diagnostics,variant_diagnostics}.py`, `src/common/linking/{threshold,diagnostic_variants}.py`, and `src/common/experiment_metadata.py` support the optional experiments. |
| Tests and outputs | `backend/app/tests/test_serving_parity.py`, `test_structure.py`, `common/test_diagnostic_variants.py`, the Python serving suite under `blockchain/test/`, the historical serving snapshots, and `outputs/diagnostics/`. |

The serving pipeline's tagged q-gram assembly, call to the legacy indexed encoder, and private use of bitarray serializers were removed from the active path. The historical shared classes remain available to the legacy RQ1 runner and original frozen tests, which assert their older formatting and sentinel behavior. Serving imports none of those classes. The AST test checks imports and definitions, and the following grep returned zero matches.

```sh
rg -n 'KeyedBloomFilter|QGramExtractor|TextPreprocessor|^\s*def (normalize|extract_qgrams|encode_record)\b' backend/app/main.py backend/app/src/rq2/harmonization_pipeline.py backend/app/src/rq2/blockchain_client.py backend/app/src/rq2/bitarray_differential_privacy.py backend/app/src/rq1/entity_resolver.py
```

### Changes to existing serving assertions

| Test file | Assertion changes |
| --- | --- |
| `blockchain/test/test_preprocessor.py` | The normalized record keeps inventory digits, removes punctuation and spaces, and includes three empty field slots. Whole-string bigrams across field boundaries replace assertions for the exact dosage, form, and pack tags. |
| `blockchain/test/test_bloom_filter.py` | Round-trip checks compare NumPy bits and the restored namespace. Width, nonempty filter, and all-zero empty filter checks remain. |
| `blockchain/test/test_similarity.py` | Uses common Dice, retains identical, disjoint and width-mismatch checks, and asserts a zero score for two empty filters. |
| `blockchain/test/test_api.py` | Adds the encoder version assertion. The previous status and request validation assertions remain. |
| `blockchain/test/test_blockchain_client.py` | Supplies versioned vectors and updates the import. The hash conversion, mock opt-in and mock gas assertions remain. |
| `blockchain/test/test_end_to_end.py`, `test_differential_privacy.py` | Provide an explicit fixture key or correct the legacy import. The behavioral assertions remain. |

### Migration before enabling writes

1. Preserve the previous ledger and export the original record IDs, descriptions, supplied dosage/form/pack, organizations and ingestion order. The contract stores packed bits and a record hash, which cannot recover those inputs.
2. For a disposable Hardhat chain, get approval to use fresh state or a separate empty deployment. The repository's existing deploy script takes `DEFAULT_BF_LENGTH=1024`, deploys the same compiled contract with a 128-byte width, and updates the local `CONTRACT_ADDRESS`. A retained chain can use a separate empty ledger with the same byte width after approval.
3. Supply the same consortium key to all writers. Start the aligned service against the empty ledger and replay records in the chosen serving order. Verify record totals, candidate version and key namespace, and publish the new cluster mapping if IDs are consumed elsewhere.
4. Update consumers that read contract cluster strings directly. The existing Python API removes the prefix. A populated legacy contract rejects replayed record IDs and hashes, and the updated client refuses its old vectors.

The contract and artifacts were left intact. Verification used mock calls and isolated off-chain runs.

## A4. Agreement after aligning the encoder

The table uses tau 0.80, the same input vectors, and all records in each bounded subset. The 200-record fixture uses seed 0. The 1,000-record columns show means over the same fixed records and three noise seeds.

| Subset | Noise | Streaming P / R / F1 | Connected P / R / F1 | Adjusted Rand |
| --- | ---: | --- | --- | ---: |
| 200 | 0% | 0.698 / 0.987 / 0.818 | 0.320 / 1.000 / 0.485 | 0.562 |
| 200 | 5% | 0.698 / 0.987 / 0.818 | 0.320 / 1.000 / 0.485 | 0.562 |
| 200 | 15% | 0.698 / 0.987 / 0.818 | 0.327 / 1.000 / 0.492 | 0.572 |
| 200 | 30% | 0.836 / 0.874 / 0.854 | 0.327 / 1.000 / 0.492 | 0.447 |
| 1,000 | 0% | 0.506 / 0.993 / 0.670 | 0.273 / 1.000 / 0.429 | 0.685 |
| 1,000 | 5% | 0.517 / 0.990 / 0.680 | 0.272 / 1.000 / 0.428 | 0.671 |
| 1,000 | 15% | 0.540 / 0.973 / 0.694 | 0.273 / 1.000 / 0.428 | 0.646 |
| 1,000 | 30% | 0.595 / 0.942 / 0.729 | 0.272 / 1.000 / 0.428 | 0.587 |

Agreement is partial even with matching bits. The fixed-leader rule sharply reduces false pairs at tau 0.80 and gives up recall at greater noise. The comparison measures the different resolvers without changing either algorithm. [Per-seed agreement](outputs/diagnostics/serving_agreement/clustering_agreement.csv)

## B1–B4. RQ1 diagnosis and recommendation

**B1.** At tau 0.86 on the golden test split, a 60-record component spanning three true entities alone contributes 77.5% of predicted pairs. The top three contribute 94.1%. At 15% noise, direct edges achieve F1 0.758, and closure adds 623 false pairs and lowers F1 to 0.625. Structured fields raise some non-match Dice scores, but there are no non-match pairs with all three fields equal on this fixture. Chaining and a permissive cutoff explain the flat aggregate metrics better than exact structured-field sharing or saturation.

**B2.** Among validation-selected composite policies, no evaluated golden-fixture point reaches F1 0.90. On the larger subset the per-noise policy reaches mean 0.910 at 0% noise. Prespecified tau 0.94 yields mean 0.928 across all larger-subset levels and seeds. The latter is a diagnostic measurement, not a deployment cutoff selected on held-out data.

**B3.** On the 1,000-record subset, single-policy mean F1 across noise is 0.886 for V0, 0.816 for V1, 0.964 for V2, and 0.891 for V3. V2's dosage token creates a separate exact-match leakage point. It also benefits from the current truth definition and from noise that leaves dosage intact. V3 changes only linkage policy and reduces component size without changing the vectors.

**B4.** Keep V0 as the default pending independent validation. Prioritize V2 in a follow-up with independent entity labels or verified dosage errors, and use V3 as the encoder-preserving comparator. A V2 or V1 promotion would require new RQ2 attacks, RQ3 evaluation and serving version and replay. A V3 promotion would require repeating RQ2 and RQ3 utility, but the RQ2 attack inputs would still use the same representation. The conclusion includes each variant's minimum change set, full file links and statistical caveats. [Detailed diagnostics and recommendation](outputs/diagnostics/rq1_overmerge/CONCLUSIONS.md)

## Verification

The original 219 configured tests passed after the serving migration. The expanded suite adds 200-record parity under three `(l,k)` choices, missing-key rejection, version and key rejection, simulated contract arguments/readback, AST enforcement, and variant behavior. The full test run uses the Python serving tests alongside the configured suite and a workspace-local temporary directory.

```text
246 passed, 1 warning in 55.36s
```

The warning is a dependency deprecation from `websockets.legacy`. No dependencies were added. Re-running the two tuned diagnostic commands reproduced their checked-in CSVs exactly.

These commands regenerate the bounded tables and figures with `backend/app` on `PYTHONPATH`.

```text
python -m experiments.rq1.serving_agreement
python -m experiments.rq1.overmerge_diagnostics
python -m experiments.rq1.tuned_diagnostics
python -m experiments.rq1.variant_diagnostics
```

## Proposed changes (not applied)

- Assess V2 with independent truth and dosage perturbation before considering a change to the RQ1 default. Evaluate deterministic-token exposure if the token would be visible to other parties.
- Record the serving randomized-response profile alongside the encoder version if deployments need to distinguish perturbation policies. The current version describes bit positions and key compatibility.
- Adopt a shared contract identifier convention across any external consumers that bypass the Python API. Gas changes from longer identifiers merit a deployment-specific measurement.
- Retire the historical encoder and preprocessor dependencies once the historical-only callers and frozen tests have a separately approved archival plan.
- Correct the undefined `stats` reference in the existing RQ2 analysis interval helper. The opt-in RQ1 diagnostics calculate t intervals independently, preserving the current RQ2 analysis code.

## Decisions for the owner

- Choose the cutover ledger and the source and order for replaying historical records.
- Confirm whether serving clients that read the contract directly can consume the qualified cluster identifiers.
- Decide whether to prioritize the independent V2 dosage-robustness evaluation or the smaller V3 linkage-only comparison.
