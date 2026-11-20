"""Custom exceptions for cp_parallel."""


class MaxWorkerError(Exception):
    """Raised when a caller explicitly requests more workers (`max_workers`) than
    are available on the machine (or, on HPC systems, than are allocated to the
    current job via CPU affinity)."""


class PlateInfoError(Exception):
    """Raised when an entry in `plate_info_dictionary` is missing required keys
    or combines keys in an invalid way (e.g. neither `path_to_images` nor
    `path_to_loaddata` is provided)."""
