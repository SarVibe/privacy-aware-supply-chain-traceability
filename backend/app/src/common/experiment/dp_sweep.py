"""Run a randomized-response parameter sweep on the fixed linkage artifacts."""

import argparse
import math
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from src.common.config import all_fields_noise, load_config, positive_integer, validate_epsilon
from src.common.data.loader import BASE_DATASET_FILENAME, LinkageData, load_linkage_data
from src.common.encoding.randomized_response import flip_probability, response_transform
from src.common.experiment.linkage import evaluate_bloom_linkage
from src.common.experiment.runner import iter_grid
from src.common.experiment_metadata import parse_standard, write_run_csv
from src.common.linking.threshold import threshold_values
from src.common.paths import prepared_dir, results_dir

Evaluator = Callable[[int, int, float], dict]
EvaluatorFactory = Callable[[LinkageData, int, float, int, tuple[float, ...]], Evaluator]


def run_response_sweep(
    argv=None, *, results_name: str, evaluator_factory: EvaluatorFactory | None = None
) -> Path:
    """Run record linkage or produce the optional privacy measurements on the same grid."""
    cfg = load_config("rq3")
    sweep, response = cfg.sweep, cfg.response_sweep
    parser = argparse.ArgumentParser(description=__doc__)
    seeds = parser.add_mutually_exclusive_group()
    seeds.add_argument("--seeds", type=int, help="number of configured prepared dataset seeds")
    seeds.add_argument("--seed-values", nargs="+", type=int)
    parser.add_argument("--noise", type=float, default=cfg.noise_levels[0])
    parser.add_argument("--configs", nargs="+", help="Bloom configurations in l:k format")
    parser.add_argument("--eps", type=float, nargs="+", help="privacy budgets, including inf for the control")
    parser.add_argument("--n-records", type=int, default=sweep.victim_draws, help="victim draws for privacy metrics")
    parser.add_argument("--max-records", type=int, help="limit prepared input by whole entity groups")
    parser.add_argument("--quick", action="store_true", help="use one seed and a bounded prepared subset")
    parser.add_argument("--all-fields", action="store_true", help="use the versioned all-field noise artifacts")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.all_fields:
        cfg = all_fields_noise(cfg)

    try:
        if args.seeds is not None and not 1 <= args.seeds <= len(cfg.seeds):
            raise ValueError("--seeds is outside the number of configured prepared seeds")
        selected_seeds = tuple(args.seed_values) if args.seed_values else cfg.seeds[:args.seeds]
        pairs = tuple(map(parse_standard, args.configs)) if args.configs else response.bloom_pairs
        budgets = tuple(map(validate_epsilon, args.eps or response.epsilons))
        draws = positive_integer(args.n_records, "n-records")
        if not set(selected_seeds) <= set(cfg.seeds):
            raise ValueError("Choose configured prepared seeds")
        for axis in (selected_seeds, pairs, budgets):
            if len(set(axis)) != len(axis):
                raise ValueError("Seeds, Bloom configurations, and epsilons must be unique")
        if args.noise not in load_config("rq1").noise_levels:
            raise ValueError("Choose a noise level available in the prepared dataset")
    except ValueError as exc:
        parser.error(str(exc))

    if args.quick:
        selected_seeds = selected_seeds[:1]
        limit = sweep.max_quick_records
        args.max_records = limit if args.max_records is None else min(limit, args.max_records)
        draws = min(limit, draws)
    taus = threshold_values(cfg.tau_grid)
    field_set = "composite"
    q = cfg.bloom.q
    results = []
    for seed in selected_seeds:
        data = load_linkage_data(cfg, seed, args.noise, field_set, max_records=args.max_records)
        measure = evaluator_factory(data, seed, args.noise, draws, taus) if evaluator_factory else None
        for point in iter_grid({"bloom_pair": pairs, "eps": budgets}):
            l, k = point["bloom_pair"]
            eps = point["eps"]
            if measure is None:
                metrics = evaluate_bloom_linkage(
                    data, args.noise, l, k, q, taus, post_transform=response_transform(seed, l, k, eps)
                )
            else:
                metrics = measure(l, k, eps)
            results.append({
                "method": "bloom", "l": l, "k": k, "q": q, "noise": args.noise, "seed": seed,
                **metrics, "eps": eps, "flip_p": flip_probability(eps, k),
            })
    output_name = response.output_csv if evaluator_factory is None else response.privacy_csv
    out = args.out or results_dir(cfg, results_name) / output_name
    write_run_csv(
        pd.DataFrame(results), out, cfg=cfg, data_mode=field_set, tau_grid=taus,
        dataset_path=str(prepared_dir(cfg) / BASE_DATASET_FILENAME), nominal_noise=args.noise,
        analysis_scope={
            "seed_values": list(selected_seeds), "bloom_pairs": pairs,
            "epsilons": [value if math.isfinite(value) else "inf" for value in budgets],
            "max_records": args.max_records, "noisy_artifacts": cfg.paths.noisy,
            "primary_metric": "unordered_cluster_pairs",
        },
    )
    print(f"saved {len(results)} rows -> {out}")
    return out
