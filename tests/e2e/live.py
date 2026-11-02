# Copyright (C) 2026 Theo van Oostrum
"""The live run's switch. The usage log and cap live in `librag.evaluation.usage`.

A live run is the e2e suite against the real AI providers, started by hand
with `scripts/e2e-live`.
"""

import os

from librag.evaluation.usage import (
    BudgetReachedError,
    ChatRecord,
    EmbeddingRecord,
    UsageLog,
    budget_usd,
)

LIVE = os.environ.get("LIBRAG_E2E_LIVE") == "1"

__all__ = [
    "LIVE",
    "BudgetReachedError",
    "ChatRecord",
    "EmbeddingRecord",
    "UsageLog",
    "budget_usd",
]
