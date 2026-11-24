"""Measure the effect of randomized response on record linkage."""

from src.common.experiment.dp_sweep import run_response_sweep


def main(argv=None):
    return run_response_sweep(argv, results_name="rq3")


if __name__ == "__main__":
    main()
