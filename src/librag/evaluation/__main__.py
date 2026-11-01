# Copyright (C) 2026 Theo van Oostrum
"""Run the retrieval evaluation: `python -m librag.evaluation fetch|run`."""

import sys

from librag.evaluation.cli import main

sys.exit(main(sys.argv[1:]))
