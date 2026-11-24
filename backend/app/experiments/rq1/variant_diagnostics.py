"""Evaluate configured optional RQ1 variants without writing the regular RQ1 outputs."""

import argparse

from experiments.rq1.overmerge_diagnostics import DEFAULT_OUTPUT
from experiments.rq1.tuned_diagnostics import tuned_evaluations, write_tuned_tables
from src.common.config import load_config
from src.common.linking.bloom import BloomLinker
from src.common.linking.diagnostic_variants import DosageBlockedBloomLinker, StarBloomLinker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", nargs="+", choices=("V0", "V1", "V2", "V3"))
    args = parser.parse_args(argv)
    cfg = load_config("rq1_diagnostics")
    choices = args.variants or cfg.diagnostics.variants
    if len(set(choices)) != len(choices):
        parser.error("Choose unique variants")
    options = {
        "V0": ("composite", lambda: BloomLinker("V0", "composite", cfg.tau_grid.start, cfg)),
        "V1": ("description", lambda: BloomLinker("V1", "description", cfg.tau_grid.start, cfg)),
        "V2": ("description", lambda: DosageBlockedBloomLinker(cfg)),
        "V3": ("composite", lambda: StarBloomLinker(cfg)),
    }
    variants = [(name, options[name][0], options[name][1]()) for name in choices]
    test_rows, validation_rows = tuned_evaluations(cfg, variants)
    write_tuned_tables(test_rows, validation_rows, "variants")
    print(f"Saved {len(test_rows)} held-out variant evaluations to {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
