# RQ2 v2 empirical collision protocol

v2 endpoints were defined after observing v1 results and are a methodological refinement, not independent confirmation of the original hypotheses.

## Design

Use the RQ1 composite encoder with filter lengths 1024, 512 and 256 crossed with hash counts 2, 4, 10 and 30. Use pre-generated, RQ1-style description-noise files at 15%. Use fresh seeds 5–9 and partition by entity within each seed into validation (25%), test (45%) and reference (30%). Pair configurations on the same records, split, noise and key within a seed. The reference entities are disjoint from both target splits. Report pairwise test-entity overlap across seeds and pilot-to-test overlap.

Baseline 1 is normalized HMAC-SHA256 exact linkage. Baseline 2 is (1024, 4), with the same validation cutoff selection as every other Bloom cell. Use a fixed secret root of at least 32 bytes in hexadecimal from `RQ2_RESEARCH_KEY`. Derive Bloom and exact keys using HMAC-SHA256 with ASCII messages `rq2:v2:bloom:{seed}` and `rq2:v2:exact:{seed}`, respectively. Record only per-seed fingerprints. Keep the v1 configuration, recommendations and results immutable. Keep the RQ1 artifacts, serving code and RQ3 behavior unchanged.

## Utility

Report common pairwise cluster precision, recall and F1, average precision on all raw unordered Dice pairs, and the 40-bin match/non-match Dice overlap. Sweep tau from 0.80 through 0.98 in steps of 0.01 using validation only, with higher tau winning F1 ties. Compute direct-edge pairwise precision, recall and F1 at the selected tau, before taking connected components. Report direct and cluster true, predicted and false pair counts so closure can be quantified.

When a cell selects 0.98, select from 0.99, 0.995 and 0.999 using validation F1 with the same tie rule. Report the result separately, with cluster and direct-edge statistics. This sensitivity comparison has no role in the primary selection.

## Privacy endpoints

Let `S(b)` be the set of tokens reaching bit `b` through any indexed HMAC, `U` the union of target and reference token vocabularies, `R` the reference vocabulary, and used bits those set in at least one target record.

- **E1. Keyed frequency alignment.** Reuse the v1 aligner. The bit-membership hit rate is the mean of the keyed membership indicator across used bits. Report `null_full = mean(|S(b)|/|U|)` and `null_matched = mean(|S(b) ∩ R|/|R|)`, plus the corresponding absolute excess and lift. Matched excess is the primary E1 endpoint. The database-frequency sensitivity uses its own candidate pool for its matched null and supplies no upper bound. The positive control uses the ordinary keyed filter with l=4096 and k=1, with mean hit at least twice the mean matched null within each split. The negative control uses 500 randomized assignments per bit from the aligner's candidate pool with an absolute error tolerance of 0.005 in every seed and split. Abort before any grid if the controls fail.
- **E2. Known-key membership.** For each target record let `C_i` contain each token in `U` whose indexed hash positions are all set. Let `T_i` be the inserted tokens. Report mean and median `|C_i ∩ T_i| / |C_i|`, mean `|C_i \\ T_i|`, and the fraction of records with `C_i = T_i`. Assert that all inserted tokens are included. Compute validation and test E2. Compare the empirical result with `|U| f` and with a per-record finite-length expectation conditional on `Q_i`. Under uniform independent placements and an absent uniform query, the latter is `(|U| - Q_i) E[(M_i / l)^k]`, where `M_i` is the number of occupied bits after `k Q_i` placements.
- **Occupancy.** Report measured fill and the mean per-record finite-length expectation `1 - (1 - 1/l)^(k Q_i)`. Label the mean-Q exponential expression as an approximation. Report occupancy entropy as the binary entropy identity. It is neither a tested hypothesis nor privacy evidence.
- **Analytical reference.** For every pair report `f = (1 - exp(-k Qbar / l))^k`, `|U| f`, and `k_opt = (l / Qbar) ln 2` using measured target Qbar. Report mean and median per-bit ambiguity over all positions.

## Hypotheses

The ideal known-key false-candidate probability decreases with l at fixed k and is U-shaped in k at fixed l, with its minimum near k_opt. No monotone k effect on empirical E2 is predicted.

- **H1'-a.** Separately for each k, mean E2 precision increases with l, and mean E2 false candidates and mean per-bit ambiguity decrease with l. Use the three seed-averaged means and descriptive pooled Spearman statistics. All three directions must be strict for a k to count. Four qualifying k values give supported, two or three give partially supported, and fewer give not supported.
- **H1'-b.** E1 matched excess does not increase as l falls. Report Spearman rho(l, matched excess) per k and paired bootstrap CIs for each cell minus Baseline 2. Supported requires the CI at every smaller-l cell to include or lie below zero. Otherwise report not supported and list the cells.
- **H1'-c.** F1 and average precision decrease as l falls, with the clearest expected evidence at k=30. Report separate verdicts by k from the three seed-averaged levels. Both strict directions support a k, one supports it partially, and neither leaves it unsupported.
- **H2'-a.** Fill increases monotonically with k for every l. Assess the seed-averaged sequence separately at each l.
- **H2'-b.** E2 false candidates have a U-shaped relationship with k. Report each length's observed argmin and analytical k_opt. A finite grid can sample only one side of a minimum. Compare the observed argmin with the analytical argmin on the same grid and describe the observed shape.
- **H2'-c.** F1 decreases when fill exceeds 0.5. Report pooled Spearman rho for fill > 0.5 and fill <= 0.5. Entropy is outside the hypothesis tests.
- **H3'.** At least one non-baseline cell has a relative reduction in mean test E2 precision of at least 25% versus Baseline 2 and mean test F1 loss of at most 0.05. Report the number of qualifying cells and paired bootstrap intervals of F1 differences. The validation recommendation is independent of this held-out classification.

Report H1'-a, H1'-b and H1'-c separately. Report mean and sample standard deviation across seeds, paired percentile bootstrap 95% intervals with zero differences retained, and corrected matched rank-biserial effect sizes. Treat all trends and intervals as descriptive because splits overlap across seeds. Report no p-values. The minimum two-sided Wilcoxon p-value at five pairs is 0.0625.

## Recommendation, robustness and execution

Choose the lowest seed-mean validation E2 precision within 0.05 of Baseline 2 validation F1. Identify eligible near-ties using paired bootstrap intervals against the winner. Report the selected cell's held-out performance in `recommendation_v2.json`. Leave downstream adoption to the owner.

Repeat at 0%, 5% and 30% description noise and at 15% all-fields noise for Baseline 2, the recommendation, and the unrestricted minimum validation E2 precision cell. Reuse a run when roles coincide. Use seed 100 with up to 60 entities as a correctness and runtime pilot, and log any entity overlap with final test splits. The pilot cannot change the protocol.

Write validated CSVs and `summary_v2.md` under `results/rq2_v2/`. Include the v1 recap, E1 and E2, analytical table, utility, direct edges, tau sensitivity, separate hypothesis verdicts, recommendation, noise cross-check, Pareto and figures. Report empirical privacy for one dataset, composite Q dependence, overlapping resamples, the role of clean structured ground-truth fields under description-only noise, and the evaluator's favorable known-key vocabulary. RQ3 addresses formal privacy.

## Protocol changelog

- Initial freeze. V2 was specified after reviewing V1. Any correction before the first V2 run requires a dated changelog entry and a commit. The endpoints, hypotheses, utility definitions and grids are frozen once V2 evaluation begins.
