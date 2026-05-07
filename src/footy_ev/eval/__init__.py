"""Evaluation: closing-line edge (CLV proxy), calibration, reliability."""

from footy_ev.eval.calibrate import (
    MIN_TRAIN_N,
    SELECTIONS,
    fit_isotonic_walk_forward,
    persist_calibration_fits,
)
from footy_ev.eval.cli import evaluate_run
from footy_ev.eval.clv import EDGE_THRESHOLD, compute_clv
from footy_ev.eval.devig import DevigMethod, devig, devig_power, devig_shin
from footy_ev.eval.reliability import (
    ACCEPTANCE_TOLERANCE,
    DEFAULT_N_BINS,
    reliability_bins,
    reliability_pass_pct,
)
from footy_ev.eval.report import write_markdown_report

__all__ = [
    "ACCEPTANCE_TOLERANCE",
    "DEFAULT_N_BINS",
    "DevigMethod",
    "EDGE_THRESHOLD",
    "MIN_TRAIN_N",
    "SELECTIONS",
    "compute_clv",
    "devig",
    "devig_power",
    "devig_shin",
    "evaluate_run",
    "fit_isotonic_walk_forward",
    "persist_calibration_fits",
    "reliability_bins",
    "reliability_pass_pct",
    "write_markdown_report",
]
