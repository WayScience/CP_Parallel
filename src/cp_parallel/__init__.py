"""cp_parallel: run CellProfiler headless in parallel across plates or wells."""

from cp_parallel.cp_parallel import results_to_log, run_parallel
from cp_parallel.exceptions import MaxWorkerError, PlateInfoError

__all__ = [
    "MaxWorkerError",
    "PlateInfoError",
    "results_to_log",
    "run_parallel",
]
