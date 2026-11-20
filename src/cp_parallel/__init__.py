"""cp_parallel: run CellProfiler headless in parallel across plates or wells."""

from importlib.metadata import PackageNotFoundError, version

from cp_parallel.cp_parallel import results_to_log, run_parallel
from cp_parallel.exceptions import MaxWorkerError, PlateInfoError

try:
    __version__ = version("cp_parallel")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "MaxWorkerError",
    "PlateInfoError",
    "results_to_log",
    "run_parallel",
]
