# RQ2 collision tuning

The empirical benchmark ran 12 Bloom configurations on 5 paired seeds at 15% description noise. The frozen RQ1 replay matched all seven fields on 10 seeds with all four frozen artifact hashes unchanged.

## Validation selection and held-out results

Validation selected (l, k) = (1024, 4) with F1 0.9378 and attack success 0.0068. The validation F1 floor was 0.8878. The lowest validation attack-success cell across the unfiltered grid was (1024, 4). Eligible near-ties by the paired validation leakage interval were (1024, 2), (512, 4).

Held-out F1 was 0.8349 for the recommendation and 0.8349 for Baseline 2. Attack success was 0.0077 and 0.0077, respectively (relative reduction 0.0%). Historical RQ1 cutoffs appear only as a secondary Baseline 2 comparison.

| method   |    l |   k | precision      | recall         | f1             | pr_auc         | dice_overlap   | attack_success   | random_baseline   | fill           |
|:---------|-----:|----:|:---------------|:---------------|:---------------|:---------------|:---------------|:-----------------|:------------------|:---------------|
| bloom    | 1024 |   2 | 0.785 +- 0.138 | 0.920 +- 0.052 | 0.838 +- 0.077 | 0.975 +- 0.008 | 0.014 +- 0.004 | 0.007 +- 0.003   | 0.003 +- 0.000    | 0.084 +- 0.001 |
| bloom    | 1024 |   4 | 0.785 +- 0.156 | 0.920 +- 0.066 | 0.835 +- 0.081 | 0.974 +- 0.007 | 0.015 +- 0.004 | 0.008 +- 0.002   | 0.004 +- 0.000    | 0.159 +- 0.002 |
| bloom    | 1024 |  10 | 0.757 +- 0.156 | 0.925 +- 0.062 | 0.820 +- 0.076 | 0.974 +- 0.005 | 0.015 +- 0.003 | 0.015 +- 0.005   | 0.010 +- 0.000    | 0.352 +- 0.006 |
| bloom    | 1024 |  30 | 0.732 +- 0.112 | 0.914 +- 0.046 | 0.806 +- 0.061 | 0.964 +- 0.010 | 0.021 +- 0.005 | 0.034 +- 0.007   | 0.029 +- 0.000    | 0.721 +- 0.008 |
| bloom    |  512 |   2 | 0.795 +- 0.157 | 0.921 +- 0.069 | 0.841 +- 0.082 | 0.974 +- 0.011 | 0.014 +- 0.004 | 0.010 +- 0.005   | 0.004 +- 0.000    | 0.160 +- 0.002 |
| bloom    |  512 |   4 | 0.795 +- 0.151 | 0.925 +- 0.059 | 0.844 +- 0.085 | 0.973 +- 0.009 | 0.015 +- 0.003 | 0.011 +- 0.005   | 0.008 +- 0.000    | 0.292 +- 0.004 |
| bloom    |  512 |  10 | 0.749 +- 0.146 | 0.915 +- 0.049 | 0.813 +- 0.081 | 0.970 +- 0.005 | 0.017 +- 0.004 | 0.029 +- 0.007   | 0.019 +- 0.000    | 0.578 +- 0.008 |
| bloom    |  512 |  30 | 0.248 +- 0.086 | 0.930 +- 0.010 | 0.385 +- 0.101 | 0.919 +- 0.010 | 0.079 +- 0.011 | 0.071 +- 0.013   | 0.057 +- 0.000    | 0.916 +- 0.006 |
| bloom    |  256 |   2 | 0.806 +- 0.170 | 0.918 +- 0.081 | 0.844 +- 0.096 | 0.973 +- 0.011 | 0.015 +- 0.005 | 0.014 +- 0.003   | 0.008 +- 0.000    | 0.294 +- 0.005 |
| bloom    |  256 |   4 | 0.751 +- 0.143 | 0.929 +- 0.062 | 0.820 +- 0.080 | 0.971 +- 0.010 | 0.018 +- 0.002 | 0.022 +- 0.006   | 0.016 +- 0.000    | 0.495 +- 0.007 |
| bloom    |  256 |  10 | 0.725 +- 0.294 | 0.889 +- 0.051 | 0.757 +- 0.233 | 0.954 +- 0.011 | 0.038 +- 0.010 | 0.037 +- 0.016   | 0.038 +- 0.000    | 0.815 +- 0.009 |
| bloom    |  256 |  30 | 0.020 +- 0.001 | 1.000 +- 0.000 | 0.038 +- 0.002 | 0.116 +- 0.023 | 0.986 +- 0.006 | 0.104 +- 0.023   | 0.111 +- 0.000    | 0.992 +- 0.001 |
| exact    |    0 |   0 | 1.000 +- 0.000 | 0.679 +- 0.010 | 0.809 +- 0.007 | 0.685 +- 0.010 | 0.321 +- 0.010 | –                | –                 | –              |

## Frequency controls

| split      |   positive_success |   random_baseline |   random_alignment |   max_random_gap |   positive_lift |
|:-----------|-------------------:|------------------:|-------------------:|-----------------:|----------------:|
| test       |           0.010395 |          0.001683 |           0.001637 |         0.000172 |        6.178328 |
| validation |           0.010486 |          0.001885 |           0.001942 |         0.000162 |        5.564029 |

The positive control uses the common encoder at l=4096 and k=1 with no bit perturbation. The gate requires positive-control lift of at least 2 in each split pooled across seeds, and random-alignment absolute error at most 0.005 in every seed and split.

## Hypotheses and paired effects

H3 was frozen at a relative attack-success reduction of 5% with an F1 loss budget of 0.05. 0 held-out grid cells met both descriptive criteria. The number of qualifying cells does not influence the validation recommendation.

H1 and H2 trends use Spearman correlations over pooled seed-specific observations within each fixed setting. The reported coefficients and seed bootstrap intervals are descriptive.

| hypothesis   | scope    | predictor   | outcome        |   n_pairs |   spearman_rho |
|:-------------|:---------|:------------|:---------------|----------:|---------------:|
| H1           | k=2      | l           | attack_success |        15 |         -0.605 |
| H1           | k=2      | l           | ambiguity_mean |        15 |         -0.946 |
| H1           | k=2      | l           | f1             |        15 |         -0.208 |
| H1           | k=2      | l           | pr_auc         |        15 |          0.113 |
| H1           | k=2      | l           | dice_overlap   |        15 |         -0.151 |
| H1           | k=4      | l           | attack_success |        15 |         -0.776 |
| H1           | k=4      | l           | ambiguity_mean |        15 |         -0.945 |
| H1           | k=4      | l           | f1             |        15 |          0.208 |
| H1           | k=4      | l           | pr_auc         |        15 |          0.170 |
| H1           | k=4      | l           | dice_overlap   |        15 |         -0.397 |
| H1           | k=10     | l           | attack_success |        15 |         -0.664 |
| H1           | k=10     | l           | ambiguity_mean |        15 |         -0.945 |
| H1           | k=10     | l           | f1             |        15 |         -0.076 |
| H1           | k=10     | l           | pr_auc         |        15 |          0.737 |
| H1           | k=10     | l           | dice_overlap   |        15 |         -0.775 |
| H1           | k=30     | l           | attack_success |        15 |         -0.927 |
| H1           | k=30     | l           | ambiguity_mean |        15 |         -0.945 |
| H1           | k=30     | l           | f1             |        15 |          0.945 |
| H1           | k=30     | l           | pr_auc         |        15 |          0.945 |
| H1           | k=30     | l           | dice_overlap   |        15 |         -0.945 |
| H2           | l=256    | k           | fill           |        20 |          0.969 |
| H2           | l=512    | k           | fill           |        20 |          0.969 |
| H2           | l=1024   | k           | fill           |        20 |          0.969 |
| H2           | fill<0.5 | fill        | entropy        |        34 |          1.000 |
| H2           | fill<0.5 | fill        | f1             |        34 |         -0.208 |
| H2           | fill>0.5 | fill        | entropy        |        26 |         -1.000 |
| H2           | fill>0.5 | fill        | f1             |        26 |         -0.698 |

Paired differences are recommendation minus Baseline 2 on the same seeds. Intervals are 95% paired percentile bootstrap intervals. Equal outcomes are retained in resampling.

The recommendation coincided with Baseline 2, so their paired difference was zero.

## Noise cross-check

| variant     |   noise |    l |   k |   f1_mean |   f1_std |   f1_delta_vs_baseline |   attack_success_mean |   attack_success_std |   attack_success_delta_vs_baseline |
|:------------|--------:|-----:|----:|----------:|---------:|-----------------------:|----------------------:|---------------------:|-----------------------------------:|
| all_fields  |  0.1500 | 1024 |   4 |    0.7656 |   0.0552 |                 0.0000 |                0.0059 |               0.0019 |                             0.0000 |
| description |  0.0000 | 1024 |   4 |    0.9398 |   0.0282 |                 0.0000 |                0.0082 |               0.0033 |                             0.0000 |
| description |  0.0500 | 1024 |   4 |    0.8448 |   0.0892 |                 0.0000 |                0.0073 |               0.0019 |                             0.0000 |
| description |  0.1500 | 1024 |   4 |    0.8349 |   0.0811 |                 0.0000 |                0.0077 |               0.0017 |                             0.0000 |
| description |  0.3000 | 1024 |   4 |    0.8134 |   0.0694 |                 0.0000 |                0.0086 |               0.0031 |                             0.0000 |

## Measurement definitions

- The adversary knows the Bloom scheme and has its own plaintext reference corpus. The evaluator holds the key. The main reference entities are disjoint from both target partitions. The database-frequency variant uses target frequencies as secondary evidence. The exported results contain only aggregate attack measurements.
- The insertion universe for each target is the union of that target's literal padded separator-delimited bigrams and the reference bigrams. Q counts distinct inserted bigrams per record. Rank quantiles map each used bit to one reference token. The evaluator tests membership in the bit's token set. Uniform random guesses draw from the evaluator universe. Ambiguity includes every bit position and counts distinct tokens once per bit.
- The collision proxy uses the measured target mean Q. Multiplying the proxy by universe size gives an approximate whole-filter false-candidate count. Per-bit ambiguity comes from the actual keyed bit memberships. Occupancy entropy is the binary entropy of the mean fill ratio.
- PR-AUC uses average precision on every unordered within-cohort pair considered by RQ1's linker. Dice overlap sums the smaller class-normalized frequency in each equal-width bin. The exact baseline uses binary equality scores.
- Secondary cross-party numbers use two seeded synthetic parties formed by a balanced partition of stable record IDs within each split. Only unordered pairs with one record in each party are eligible. They use the same cluster labels and entity IDs as the primary metric and do not measure real organization effects.

## Limitations

- These are empirical measurements for one frequency-alignment attack, one threat model, one shipment dataset and one composite representation. RQ3 addresses formal differential privacy.
- The default typo generator changes only descriptions. Dosage, dosage form and pack size remain available to the encoder and also contribute to ground truth. The optional all-fields row uses separately prepared artifacts.
- Both the collision proxy and occupancy depend on composite Q. Saturated filters amplify accidental membership and ties, and can increase raw attack success even as ambiguity grows. A known-key analysis here is analytical only.
- Reference and target entities come from the same prepared shipment population and differ in their realized distributions. A single pilot fold and five partially overlapping resamples limit uncertainty interpretation. Control lift and near-ties can vary with the experimental keys and splits.
