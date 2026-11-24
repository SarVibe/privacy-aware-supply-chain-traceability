"""Command alias for preparing the versioned RQ1 noisy records."""

import sys

from experiments.rq1.prepare_rq1_data import main


if __name__ == "__main__":
    main(["--stage", "noise", *sys.argv[1:]])
