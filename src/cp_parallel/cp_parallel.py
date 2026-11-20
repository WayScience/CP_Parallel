"""
Run CellProfiler headless across many plates (or wells) in parallel, and write a
log file per run.

This module consolidates the `cp_parallel.py` / `cp_utils.py` helper that has been
copy-pasted (and independently patched) across several Way Science repositories.
It supports the union of features that have accumulated across those copies:

- A single plate, or many plates, processed in parallel.
- Grouping at the plate level or the well level (``group_level``).
- Input as a directory of images (``path_to_images``) or a LoadData CSV
  (``path_to_loaddata``).
- Batch processing: restrict a run to an image-set range via per-entry
  ``first_image_set`` / ``last_image_set``, and cap concurrency independent of
  batch size via ``max_workers`` (useful for timelapse datasets, checkpointing a
  long run, or managing memory on a large LoadData CSV).
- HPC compatibility: CPU-count detection that respects job/cgroup CPU affinity
  (rather than the full host's core count), and optional execution inside an
  Apptainer/Singularity container (``run_with_apptainer``).
- Optional CellProfiler plugins directory, either for all plates (``plugins_dir``)
  or per-plate (``plugins_directory`` key in a plate's info dict).
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any, Literal, NamedTuple, Union

from cp_parallel.exceptions import MaxWorkerError, PlateInfoError

# Set up a module-level logger for this package.
logger = logging.getLogger(__name__)

# Custom type aliases for clarity in function signatures.
# NOTE: this is a runtime expression, not an annotation, so `from __future__ import
# annotations` does not protect it -- it must use `typing.Union`, not `str | pathlib.Path`
# (the PEP 604 `|` syntax only works as a *runtime* expression on Python 3.10+).
PathLike = Union[str, pathlib.Path]
GroupLevel = Literal["plate", "well"]


class _JobSpec(NamedTuple):
    """A single CellProfiler invocation, and the metadata needed to log it."""

    # Name of the type of run (e.g. "illum_correction"), used in the log file name.
    name: str
    # The parent plate name, used to group log files when group_level="well".
    plate_name: str
    # The command to run CellProfiler (optionally wrapped in a container runtime).
    command: list[str]


def _get_available_cpu_count() -> int:
    """
    Return the number of CPUs available to this process.

    On Linux (including HPC schedulers such as SLURM that constrain a job to a
    CPU subset via cgroups), ``os.sched_getaffinity`` reflects the actual
    allocation. ``os.cpu_count()`` reports the host's total core count, which can
    over-commit workers on a shared HPC node, so it is only used as a fallback.
    """
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _find_container_runtime() -> str:
    """Locate an Apptainer or Singularity executable on PATH for container runs."""
    for runtime in ("apptainer", "singularity"):
        if shutil.which(runtime) is not None:
            return runtime
    raise OSError(
        "Neither 'apptainer' nor 'singularity' was found on PATH. Install one of "
        "these containerization tools, or omit `run_with_apptainer`, to continue."
    )


def _resolve_plugins_dir(
    info: dict[str, Any], plugins_dir: PathLike | None
) -> PathLike | None:
    """Per-plate `plugins_directory` takes priority over the function-wide default."""
    resolved = info.get("plugins_directory", plugins_dir)
    if resolved is None:
        return None
    if not pathlib.Path(resolved).is_dir():
        raise FileNotFoundError(
            f"Plugins directory '{resolved}' does not exist or is not a directory."
        )
    return resolved


def _build_command(
    name: str,
    info: dict[str, Any],
    group_level: GroupLevel,
    plugins_dir: PathLike | None,
    run_with_apptainer: PathLike | None,
    conserve_memory: bool,
) -> list[str]:
    """Build the `cellprofiler` (optionally container-wrapped) command for one entry."""
    # Gather the required paths from the entry's info dict.
    path_to_pipeline = info["path_to_pipeline"]
    path_to_output = info["path_to_output"]

    # Raise errors for missing files/directories, and create the output directory if
    # it doesn't exist.
    if not pathlib.Path(path_to_pipeline).is_file():
        raise FileNotFoundError(
            f"The file '{pathlib.Path(path_to_pipeline).name}' does not exist."
        )
    pathlib.Path(path_to_output).mkdir(parents=True, exist_ok=True)

    has_images = "path_to_images" in info
    has_loaddata = "path_to_loaddata" in info
    if has_images == has_loaddata:
        raise PlateInfoError(
            f"Entry '{name}' must specify exactly one of 'path_to_images' or "
            "'path_to_loaddata'."
        )

    # Build the base CellProfiler command, which is the same for all entries.
    cellprofiler_command = ["cellprofiler", "-c", "-r", "-p", str(path_to_pipeline)]

    # Add the input source (images directory or LoadData CSV) to the command.
    if has_loaddata:
        path_to_loaddata = info["path_to_loaddata"]
        if not pathlib.Path(path_to_loaddata).is_file():
            raise FileNotFoundError(
                f"File '{pathlib.Path(path_to_loaddata).name}' does not exist or "
                "is not a file."
            )
        cellprofiler_command += ["--data-file", str(path_to_loaddata)]
    else:
        path_to_images = info["path_to_images"]
        if not pathlib.Path(path_to_images).is_dir():
            raise FileNotFoundError(
                f"Directory '{pathlib.Path(path_to_images).name}' does not exist "
                "or is not a directory."
            )
        cellprofiler_command += ["-i", str(path_to_images)]

    cellprofiler_command += ["-o", str(path_to_output)]

    if group_level == "well":
        cellprofiler_command += ["-g", f"Well={name}"]

    if "first_image_set" in info:
        cellprofiler_command += ["-f", str(info["first_image_set"])]
    if "last_image_set" in info:
        cellprofiler_command += ["-l", str(info["last_image_set"])]

    if conserve_memory:
        cellprofiler_command += ["--conserve-memory", "True"]

    resolved_plugins_dir = _resolve_plugins_dir(info, plugins_dir)
    if resolved_plugins_dir is not None:
        cellprofiler_command += ["--plugins-directory", str(resolved_plugins_dir)]

    if run_with_apptainer is not None:
        runtime = _find_container_runtime()
        return [runtime, "exec", str(run_with_apptainer), *cellprofiler_command]

    return cellprofiler_command


def results_to_log(
    results: list[subprocess.CompletedProcess],
    log_dir: PathLike,
    run_name: str,
    jobs: list[_JobSpec] | None = None,
    group_level: GroupLevel = "plate",
) -> None:
    """
    Write one log file per CellProfiler process, capturing its stderr output.

    Args:
        results: outputs from `subprocess.run`, in the same order as `jobs`.
        log_dir: directory to write log files into.
        run_name: a name for this type of CellProfiler run (e.g. "illum_correction"),
            used in each log file's name.
        jobs: the `_JobSpec` entries that produced `results`, in matching order.
            Required to name/organize log files; omitted only for backwards
            compatibility with older callers that invoke this function directly
            with plate names baked into `run_name`.
        group_level: when "well", log files are nested under a per-plate
            subdirectory (`log_dir/<plate_name>/<well>_<run_name>_run.log`);
            when "plate", log files are written flat.
    """
    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    if jobs is None:
        # Fallback used only when results_to_log is called without job metadata.
        jobs = [
            _JobSpec(name=f"process_{index}", plate_name="", command=[])
            for index in range(len(results))
        ]

    for result, job in zip(results, jobs):
        output_string = (
            result.stderr.decode("utf-8")
            if isinstance(result.stderr, bytes)
            else str(result.stderr)
        )

        if group_level == "well" and job.plate_name:
            target_dir = log_dir / job.plate_name
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            target_dir = log_dir

        log_file_path = target_dir / f"{job.name}_{run_name}_run.log"
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(output_string)


def run_parallel(
    plate_info_dictionary: dict[str, dict[str, Any]],
    run_name: str,
    group_level: GroupLevel = "plate",
    max_workers: int | Literal["all"] | None = None,
    log_dir: PathLike = "./logs",
    plugins_dir: PathLike | None = None,
    run_with_apptainer: PathLike | None = None,
    conserve_memory: bool = False,
) -> list[subprocess.CompletedProcess]:
    """
    Run CellProfiler headless on one or many plates/wells in parallel.

    Args:
        plate_info_dictionary: maps a plate (or well) name to a dict of info to
            run CellProfiler. Each entry must include:

            - ``path_to_pipeline``: path to the `.cppipe` pipeline file.
            - ``path_to_output``: path to the output directory (created if
              missing).
            - exactly one of:
                - ``path_to_images``: path to a directory of images, or
                - ``path_to_loaddata``: path to a LoadData CSV.

            Each entry may optionally include:

            - ``plate_name``: required when `group_level="well"` -- the parent
              plate this well belongs to, used to group log files.
            - ``plugins_directory``: overrides `plugins_dir` for this entry.
            - ``first_image_set`` / ``last_image_set``: restrict the run to an
              image-set range (``-f``/``-l``), useful for splitting a large run
              into batches (e.g. a timelapse dataset, or checkpointing a long
              run) across multiple calls.

            A single-plate run is just a dictionary with one entry; this
            function does not require more than one plate to be useful.
        run_name: a name for this type of CellProfiler run (e.g.
            "whole_image_qc"), used in log file names.
        group_level: "plate" (default) or "well". At the well level, each
            command is restricted to its well via CellProfiler's `-g Well=...`
            grouping flag, and log files are nested per plate.
        max_workers: maximum number of CellProfiler processes to run at once.
            Defaults to the number of entries in `plate_info_dictionary`, capped
            to the number of CPUs available to this process (see
            `_get_available_cpu_count`). If explicitly set higher than the
            available CPU count, raises `MaxWorkerError` rather than
            silently oversubscribing the machine/job. Pass ``-1`` or ``"all"``
            to use every CPU available to this process.
        log_dir: directory to write one log file per process into.
        plugins_dir: path to a CellProfiler plugins directory, if your pipeline
            uses plugin modules. Applies to all entries unless overridden by a
            `plugins_directory` key on an individual entry.
        run_with_apptainer: path to an Apptainer/Singularity image (`.sif`).
            When set, CellProfiler is run inside that container via `apptainer
            exec`/`singularity exec` (whichever is found on PATH), which is the
            typical way to run CellProfiler headless on an HPC cluster.
        conserve_memory: adds CellProfiler's `--conserve-memory True` flag,
            which trades speed for a smaller memory footprint -- useful for
            large runs with many image sets.

    Returns:
        The `subprocess.CompletedProcess` for each plate/well, in the order the
        corresponding entries were run.

    Raises:
        FileNotFoundError: if a pipeline, image directory, LoadData CSV, or
            plugins directory does not exist.
        PlateInfoError: if an entry specifies both or neither of
            `path_to_images` / `path_to_loaddata`, or is missing `plate_name`
            when `group_level="well"`.
        MaxWorkerError: if `max_workers` is explicitly set higher than the
            number of CPUs available to this process.
        ValueError: if `max_workers` is not a positive integer, ``-1``,
            ``"all"``, or ``None``.
        EnvironmentError: if `run_with_apptainer` is set but neither
            `apptainer` nor `singularity` is available on PATH.
    """
    if group_level not in ("plate", "well"):
        raise ValueError("group_level must be either 'plate' or 'well'.")

    jobs: list[_JobSpec] = []
    for name, info in plate_info_dictionary.items():
        if group_level == "well" and "plate_name" not in info:
            raise PlateInfoError(
                f"Missing 'plate_name' for well '{name}'. Each entry must include "
                "'plate_name' when group_level='well'."
            )
        plate_name = info.get("plate_name", name)

        command = _build_command(
            name=name,
            info=info,
            group_level=group_level,
            plugins_dir=plugins_dir,
            run_with_apptainer=run_with_apptainer,
            conserve_memory=conserve_memory,
        )
        jobs.append(_JobSpec(name=name, plate_name=plate_name, command=command))

    available_cpus = _get_available_cpu_count()
    if max_workers is None:
        num_workers = min(len(jobs), available_cpus) or 1
    elif max_workers == "all" or max_workers == -1:
        num_workers = available_cpus
    elif (
        isinstance(max_workers, bool)
        or not isinstance(max_workers, int)
        or max_workers < 1
    ):
        raise ValueError(
            f"max_workers must be a positive integer, -1, 'all', or None; "
            f"got {max_workers!r}."
        )
    elif max_workers > available_cpus:
        raise MaxWorkerError(
            f"Requested max_workers={max_workers} exceeds the {available_cpus} "
            "CPU(s) available to this process. Reduce max_workers or request "
            "more CPUs for this job."
        )
    else:
        num_workers = max_workers

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures: list[Future] = [
            executor.submit(subprocess.run, args=job.command, capture_output=True)
            for job in jobs
        ]
        results: list[subprocess.CompletedProcess] = [
            future.result() for future in futures
        ]

    logger.info("All %d CellProfiler process(es) have completed.", len(results))

    results_to_log(
        results=results,
        log_dir=log_dir,
        run_name=run_name,
        jobs=jobs,
        group_level=group_level,
    )

    for job, result in zip(jobs, results):
        if result.returncode != 0:
            logger.error(
                "CellProfiler exited with return code %d for '%s'. See the log "
                "file in %s for details.",
                result.returncode,
                job.name,
                log_dir,
            )

    logger.info("All results have been written to log files in %s.", log_dir)

    return results
