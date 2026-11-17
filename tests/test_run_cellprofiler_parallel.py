"""
End-to-end tests for run_cellprofiler_parallel.

These tests never invoke a real `cellprofiler` binary: `ProcessPoolExecutor` is
swapped for `ThreadPoolExecutor` (so mocks applied in the test process are
visible to the "worker"), and `subprocess.run` is replaced with a fake that
returns a canned `CompletedProcess` based on the command it was given.
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

import cp_parallel.cp_parallel as cp_parallel_module
from cp_parallel.exceptions import MaxWorkerError, PlateInfoError


@pytest.fixture(autouse=True)
def use_thread_pool_executor(monkeypatch):
    """Run "parallel" jobs on threads so in-process mocks apply to every job."""
    monkeypatch.setattr(cp_parallel_module, "ProcessPoolExecutor", ThreadPoolExecutor)


@pytest.fixture
def fake_cellprofiler_run(monkeypatch):
    """Replace subprocess.run with a fake that never shells out to CellProfiler."""
    calls = []

    def _fake_run(args, capture_output=True):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=b"", stderr=b"Success.\n"
        )

    monkeypatch.setattr(cp_parallel_module.subprocess, "run", _fake_run)
    return calls


def test_single_plate_run(
    pipeline_file, images_dir, output_dir, log_dir, fake_cellprofiler_run
):
    plate_info_dictionary = {
        "Plate1": {
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        }
    }

    results = cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary=plate_info_dictionary,
        run_name="whole_image_qc",
        log_dir=log_dir,
    )

    assert len(results) == 1
    assert results[0].returncode == 0
    assert len(fake_cellprofiler_run) == 1

    log_file = log_dir / "Plate1_whole_image_qc_run.log"
    assert log_file.is_file()
    assert log_file.read_text() == "Success.\n"


def test_multi_plate_run(
    pipeline_file, images_dir, output_dir, log_dir, fake_cellprofiler_run
):
    plate_info_dictionary = {
        f"Plate{i}": {
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir / f"Plate{i}",
        }
        for i in range(1, 4)
    }

    results = cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary=plate_info_dictionary,
        run_name="analysis",
        log_dir=log_dir,
    )

    assert len(results) == 3
    assert len(fake_cellprofiler_run) == 3
    for i in range(1, 4):
        assert (log_dir / f"Plate{i}_analysis_run.log").is_file()


def test_well_level_run_nests_logs_under_plate(
    pipeline_file, images_dir, output_dir, log_dir, fake_cellprofiler_run
):
    plate_info_dictionary = {
        "A01": {
            "plate_name": "Plate1",
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        "A02": {
            "plate_name": "Plate1",
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
    }

    cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary=plate_info_dictionary,
        run_name="well_qc",
        group_level="well",
        log_dir=log_dir,
    )

    assert (log_dir / "Plate1" / "A01_well_qc_run.log").is_file()
    assert (log_dir / "Plate1" / "A02_well_qc_run.log").is_file()
    # Each well's command should be restricted to that well.
    well_flags = {args[args.index("-g") + 1] for args in fake_cellprofiler_run}
    assert well_flags == {"Well=A01", "Well=A02"}


def test_well_level_missing_plate_name_raises(
    pipeline_file, images_dir, output_dir, log_dir
):
    plate_info_dictionary = {
        "A01": {
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        }
    }

    with pytest.raises(PlateInfoError):
        cp_parallel_module.run_cellprofiler_parallel(
            plate_info_dictionary=plate_info_dictionary,
            run_name="well_qc",
            group_level="well",
            log_dir=log_dir,
        )


def test_invalid_group_level_raises(pipeline_file, images_dir, output_dir, log_dir):
    with pytest.raises(ValueError):
        cp_parallel_module.run_cellprofiler_parallel(
            plate_info_dictionary={
                "Plate1": {
                    "path_to_pipeline": pipeline_file,
                    "path_to_images": images_dir,
                    "path_to_output": output_dir,
                }
            },
            run_name="run",
            group_level="field",  # type: ignore[arg-type]
            log_dir=log_dir,
        )


def test_max_workers_within_limit_is_used(
    pipeline_file, images_dir, output_dir, log_dir, fake_cellprofiler_run, monkeypatch
):
    monkeypatch.setattr(cp_parallel_module, "_get_available_cpu_count", lambda: 8)
    recorded_max_workers = {}
    real_executor = ThreadPoolExecutor

    class RecordingExecutor(real_executor):
        def __init__(self, max_workers=None, *args, **kwargs):
            recorded_max_workers["value"] = max_workers
            super().__init__(*args, max_workers=max_workers, **kwargs)

    monkeypatch.setattr(cp_parallel_module, "ProcessPoolExecutor", RecordingExecutor)

    plate_info_dictionary = {
        "Plate1": {
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        }
    }

    cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary=plate_info_dictionary,
        run_name="run",
        max_workers=4,
        log_dir=log_dir,
    )

    assert recorded_max_workers["value"] == 4


def test_max_workers_exceeding_available_cpus_raises(
    pipeline_file, images_dir, output_dir, log_dir, monkeypatch
):
    monkeypatch.setattr(cp_parallel_module, "_get_available_cpu_count", lambda: 2)

    with pytest.raises(MaxWorkerError):
        cp_parallel_module.run_cellprofiler_parallel(
            plate_info_dictionary={
                "Plate1": {
                    "path_to_pipeline": pipeline_file,
                    "path_to_images": images_dir,
                    "path_to_output": output_dir,
                }
            },
            run_name="run",
            max_workers=16,
            log_dir=log_dir,
        )


def test_default_max_workers_caps_to_available_cpus(
    pipeline_file, images_dir, output_dir, log_dir, monkeypatch
):
    monkeypatch.setattr(cp_parallel_module, "_get_available_cpu_count", lambda: 2)
    recorded_max_workers = {}
    real_executor = ThreadPoolExecutor

    class RecordingExecutor(real_executor):
        def __init__(self, max_workers=None, *args, **kwargs):
            recorded_max_workers["value"] = max_workers
            super().__init__(*args, max_workers=max_workers, **kwargs)

    monkeypatch.setattr(cp_parallel_module, "ProcessPoolExecutor", RecordingExecutor)
    monkeypatch.setattr(
        cp_parallel_module.subprocess,
        "run",
        lambda args, capture_output=True: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=b"", stderr=b""
        ),
    )

    plate_info_dictionary = {
        f"Plate{i}": {
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir / f"Plate{i}",
        }
        for i in range(1, 6)  # 5 plates requested, only 2 CPUs available
    }

    cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary=plate_info_dictionary,
        run_name="run",
        log_dir=log_dir,
    )

    assert recorded_max_workers["value"] == 2


def test_nonzero_returncode_is_logged(
    pipeline_file, images_dir, output_dir, log_dir, monkeypatch, caplog
):
    monkeypatch.setattr(
        cp_parallel_module.subprocess,
        "run",
        lambda args, capture_output=True: subprocess.CompletedProcess(
            args=args, returncode=1, stdout=b"", stderr=b"boom\n"
        ),
    )

    with caplog.at_level(logging.ERROR, logger=cp_parallel_module.__name__):
        cp_parallel_module.run_cellprofiler_parallel(
            plate_info_dictionary={
                "Plate1": {
                    "path_to_pipeline": pipeline_file,
                    "path_to_images": images_dir,
                    "path_to_output": output_dir,
                }
            },
            run_name="run",
            log_dir=log_dir,
        )

    assert any("Plate1" in message for message in caplog.messages)
    assert (log_dir / "Plate1_run_run.log").read_text() == "boom\n"


def test_loaddata_csv_run(
    pipeline_file, loaddata_csv, output_dir, log_dir, fake_cellprofiler_run
):
    cp_parallel_module.run_cellprofiler_parallel(
        plate_info_dictionary={
            "Plate1": {
                "path_to_pipeline": pipeline_file,
                "path_to_loaddata": loaddata_csv,
                "path_to_output": output_dir,
            }
        },
        run_name="run",
        log_dir=log_dir,
    )

    (command,) = fake_cellprofiler_run
    assert "--data-file" in command


def test_image_set_batches_share_log_dir_without_collisions(
    pipeline_file, loaddata_csv, output_dir, log_dir, fake_cellprofiler_run
):
    """Simulates a large run split into image-set batches, one call per batch."""
    for batch_index, (first, last) in enumerate([(1, 50), (51, 100)]):
        cp_parallel_module.run_cellprofiler_parallel(
            plate_info_dictionary={
                f"batch_{batch_index}": {
                    "path_to_pipeline": pipeline_file,
                    "path_to_loaddata": loaddata_csv,
                    "path_to_output": output_dir,
                    "first_image_set": first,
                    "last_image_set": last,
                }
            },
            run_name="batch_analysis",
            max_workers=1,
            log_dir=log_dir,
        )

    assert (log_dir / "batch_0_batch_analysis_run.log").is_file()
    assert (log_dir / "batch_1_batch_analysis_run.log").is_file()
    assert len(fake_cellprofiler_run) == 2
    assert fake_cellprofiler_run[0][fake_cellprofiler_run[0].index("-f") + 1] == "1"
    assert fake_cellprofiler_run[1][fake_cellprofiler_run[1].index("-l") + 1] == "100"
