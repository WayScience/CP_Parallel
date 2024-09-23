"""
This module defines custom exceptions for cp_parallel.
"""

class MaxWorkerError(Exception):
    """
    Raised when the number of workers assigned to `max_workers` exceeds the number of CPU/workers on the machine. 
    """
    pass
