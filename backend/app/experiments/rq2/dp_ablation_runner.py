"""Evaluate RQ2 privacy metrics on the same randomized-response grid as RQ3."""

from src.common.experiment.dp_sweep import run_response_sweep
from src.rq2.privacy_pipeline import build_scenario, run_bloom
from src.rq2.rq2_dataset import privacy_dataset


def _privacy_evaluator(data, seed, noise, draws, taus):
    ds = privacy_dataset(data, seed, noise)
    cfg = data.config
    sweep, q = cfg.sweep, cfg.bloom.q
    scenario = build_scenario(ds, seed, noise, sweep.overlap, draws, q, dict_extra_ratio=sweep.dict_extra_ratio)

    def evaluate(l, k, eps):
        return run_bloom(ds, scenario, l, k, q, eps=eps, bit_top=sweep.bit_top, taus=taus)

    return evaluate


def main(argv=None):
    return run_response_sweep(argv, results_name="rq2", evaluator_factory=_privacy_evaluator)


if __name__ == "__main__":
    main()
