# RQ2 v1 post-hoc supplement

This supplement is post-hoc, defined after seeing v1 results. It derives from the saved primary per-run CSV at 15% description noise. It uses 12 configurations on five paired seed resamples and does not rerun v1.

Raw bit-membership hit rate is confounded by collision-induced growth of the random success probability |S(b)|/|U|. The full-universe absolute excess subtracts that baseline, and lift divides by it. The aligner's reference-only candidate pool differs from the evaluator universe. V1's key was ephemeral and the aggregate CSVs cannot recover the candidate-matched null or known-key metrics.

The paired table compares each of the 11 other cells with Baseline 2 (1024, 4), using cell minus baseline. The 95% intervals are paired percentile bootstrap intervals with zero differences retained. Seeds are overlapping resamples of one dataset. These measurements are descriptive and empirical.
