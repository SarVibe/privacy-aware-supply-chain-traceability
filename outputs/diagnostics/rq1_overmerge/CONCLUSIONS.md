# RQ1 over-merging diagnostics

The 200-record golden uses its original seed-0 split, with 60 validation and 140 test records. The second subset contains the same 1,000 records across seeds 0, 1, and 2. It keeps whole entity groups selected once by a seeded permutation and uses the original saved split for each seed. The 1,000-record test partitions contain 745, 686, and 821 records. All inputs use the existing noisy artifacts.

## B1. Where the false links accumulate

At tau 0.86, the top three golden-fixture test components account for 94.1% of predicted pairs at 0%, 5%, and 15% noise. Their sizes are 60, 20, and 20. The 60-record component spans three true entities and contributes 1,770 of 2,284 predicted pairs by itself. All 140 test cluster assignments are identical at the first three noise levels even as direct edges change. Transitive closure adds 598, 605, and 623 false pairs at those levels. It adds 772 at 30%.

| Noise | Direct edge P / R / F1 | Cross-party F1 | Connected P / R / F1 |
| ---: | --- | ---: | --- |
| 0% | 0.612 / 0.988 / 0.756 | 0.756 | 0.454 / 1.000 / 0.625 |
| 5% | 0.614 / 0.983 / 0.755 | 0.756 | 0.454 / 1.000 / 0.625 |
| 15% | 0.619 / 0.978 / 0.758 | 0.757 | 0.454 / 1.000 / 0.625 |
| 30% | 0.670 / 0.929 / 0.778 | 0.770 | 0.449 / 0.981 / 0.616 |

Direct edges are unordered noisy-side pairs before closure. The cross-party check compares clean against noisy records, omits identical record IDs, and counts same-entity matches. It complements the noisy-side check, which isolates how closure changes the very same edges. [Threshold metrics](threshold_metrics.csv) · [Cluster sizes](component_sizes.csv) · [Largest components](large_components.csv)

At 0% noise on the golden test split, the non-match Dice 95th percentile rises from 0.859 for description-only to 0.881 for the composite. Median distinct q-gram counts are 36 and 44, and mean fill rises from 0.137 to 0.161. The corresponding expected means are 0.135 and 0.160. About 19.1% of composite grams are absent from the corresponding description-only sets, including separator-boundary grams. These fill values give little evidence that saturation drives the result.

The golden test split has no non-match pairs that share all three normalized structured fields. On the 1,000-record subset at 0% noise, such pairs account for 0.57–0.97% of non-match record pairs across splits. Their average seed-wise median Dice rises from 0.568 for description-only to 0.640 for composite. The composite still has a high-scoring non-match tail outside that group. [Dice quantiles](dice_quantiles.csv) · [Structured-field overlap](structured_sharing.csv) · [Encoding distributions](encoding_distributions.csv) · [200-record histogram](dice_golden_200.png) · [1,000-record histogram](dice_fixed_1000.png)

Chaining is the main reason the fixture metrics stay flat. Tau 0.86 already admits false direct edges, and closure amplifies them. Structured-field overlap raises some non-match scores, while exact sharing of all three fields cannot explain the golden-fixture merges. On the larger subset, increasing the fixed diagnostic tau from 0.86 to 0.94 reduces mean closure-added false pairs from 3,777 to 90 and increases mean cluster F1 from 0.676 to 0.928.

## B2. Validation-tuned composite

The shared RQ1 sweep uses validation entities only and breaks F1 ties toward the higher tau. Single tau maximizes mean validation F1 across noise levels for each seed. Per-noise tau repeats selection independently. Test results use separate entities. The summary includes mean precision, recall, F1 and untruncated 95% t intervals over seeds. The golden fixture has one seed, so its intervals are blank. The larger subset has three splits of a shared population.

| Noise | 1,000-record single P / R / F1 | 1,000-record per-level P / R / F1 | Per-level F1 95% CI |
| ---: | --- | --- | --- |
| 0% | 0.843 / 0.971 / 0.898 | 0.868 / 0.970 / 0.910 | 0.676–1.144 |
| 5% | 0.843 / 0.963 / 0.894 | 0.845 / 0.961 / 0.894 | 0.690–1.099 |
| 15% | 0.842 / 0.956 / 0.890 | 0.844 / 0.952 / 0.890 | 0.693–1.087 |
| 30% | 0.810 / 0.945 / 0.861 | 0.812 / 0.953 / 0.865 | 0.600–1.130 |

Composite F1 reaches 0.90 in the larger evaluation. The validation-selected per-level policy reaches mean 0.910 at 0% noise, and the prespecified fixed tau 0.94 produces mean 0.928 across the four levels and three splits. The golden fixture peaks at 0.887 among the tested fixed and validation-selected policies. The result supports reachability on the larger subset and does not establish a 0.90 guarantee. [Selected test rows](tuned_composite_test.csv) · [Validation sweep](tuned_composite_validation.csv) · [Means and intervals](tuned_composite_summary.csv)

## B3. Alternative linkage variants

The diagnostic runner uses the variants listed in `backend/app/configs/rq1_diagnostics.yaml`, with an optional `--variants` override. It uses the same splits, noise levels, grid, and validation policy as B2. V0 exactly reproduces the B2 outputs. V1 reuses the existing description-only linker. V2 links description vectors only when normalized dosage HMACs match. Missing dosage matches other missing dosage. V3 uses the original composite vector and assigns to the closest eligible fixed leader in CSV order.

| Variant | 200-record single F1, 0/5/15/30% | 1,000-record single F1, 0/5/15/30% |
| --- | --- | --- |
| V0 composite | 0.625 / 0.625 / 0.625 / 0.616 | 0.898 / 0.894 / 0.890 / 0.861 |
| V1 description | 0.788 / 0.788 / 0.774 / 0.729 | 0.826 / 0.821 / 0.816 / 0.802 |
| V2 dosage block | 0.871 / 0.871 / 0.849 / 0.792 | 0.965 / 0.964 / 0.963 / 0.964 |
| V3 star | 0.788 / 0.788 / 0.770 / 0.677 | 0.894 / 0.900 / 0.890 / 0.880 |

With per-noise tuning on the larger subset, V2 averages F1 0.975 across noise levels, versus 0.890 for V0 and 0.899 for V3. The mean largest component falls from 46.7 records for V0 to 25.9 for V2 and 36.6 for V3. The corresponding top-three shares are 26.4%, 13.1%, and 21.6%. The tables include per-level precision, recall, cluster counts, largest component sizes, truth spans, and intervals for both policies. [Held-out rows](variants_test.csv) · [Validation sweeps](variants_validation.csv) · [Summary with intervals](variants_summary.csv)

| Variant | Minimum change and downstream impact |
| --- | --- |
| V0 with a recalibrated tau | Change the threshold policy after independent validation. Recompute RQ2 and RQ3 utility for the changed policy. The vectors and RQ2 attack inputs stay the same. |
| V1 | Switch the field set. Re-run RQ2 attacks and RQ3 on description vectors. Deployment would need a new encoder version and vector replay. |
| V2 | Add dosage blocking and use description Bloom vectors. Re-run RQ2 attacks and measure leakage from the deterministic dosage token separately. RQ3 would need an explicit privacy policy for the token because flipping the Bloom bits leaves it intact. Deployment would need candidate blocking, a version change, and vector replay. |
| V3 | Change the clustering rule while retaining the encoder. Re-run RQ2 utility and RQ3 linkage at each epsilon. The existing RQ2 attack inputs remain comparable. Serving already uses fixed leaders. Matching the evaluation requires the same tau, order, and tie policy. |

## B4. Recommendation

Keep V0 as the default for now. V2 is the strongest candidate for a follow-up experiment. Dosage contributes to the current truth construction and is unperturbed in these inputs. Independent entity labels or validated dosage errors would test whether V2 retains its advantage when exact dosage is unreliable. Its deterministic token also exposes repeated dosage equality if observable. V3 is the smaller change for studying chaining with the current encoder, but its average benefit is modest on the larger subset and its recall falls at high noise. The minimum follow-up is an independently validated threshold and a side-by-side replay of V0, V2, and V3 on the same splits. Promotion of any variant should follow that comparison and the applicable downstream checks.
