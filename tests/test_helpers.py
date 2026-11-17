"""Unit tests for small helpers: CPU-count detection and results_to_log."""

import os
import subprocess

import pytest

from cp_parallel.cp_parallel import (
    _find_container_runtime,
    _get_available_cpu_count,
    _JobSpec,
    results_to_log,
)


def test_available_cpu_count_uses_sched_affinity(monkeypatch):
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1, 2}, raising=False)
    assert _get_available_cpu_count() == 3


def test_available_cpu_count_falls_back_without_affinity(monkeypatch):
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    assert _get_available_cpu_count() == 4


def test_find_container_runtime_prefers_apptainer(monkeypatch):
    monkeypatch.setattr(
        "cp_parallel.cp_parallel.shutil.which",
        lambda runtime: f"/usr/bin/{runtime}",
    )
    assert _find_container_runtime() == "apptainer"


def test_find_container_runtime_raises_when_neither_present(monkeypatch):
    monkeypatch.setattr("cp_parallel.cp_parallel.shutil.which", lambda runtime: None)
    with pytest.raises(EnvironmentError):
        _find_container_runtime()


def test_results_to_log_flat_for_plate_level(tmp_path):
    jobs = [_JobSpec(name="Plate1", plate_name="Plate1", command=[])]
    results = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"ok\n")
    ]

    results_to_log(results=results, log_dir=tmp_path, run_name="run", jobs=jobs)

    assert (tmp_path / "Plate1_run_run.log").read_text() == "ok\n"


def test_results_to_log_nests_by_plate_for_well_level(tmp_path):
    jobs = [
        _JobSpec(name="A01", plate_name="Plate1", command=[]),
        _JobSpec(name="B01", plate_name="Plate2", command=[]),
    ]
    results = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"a\n"),
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"b\n"),
    ]

    results_to_log(
        results=results,
        log_dir=tmp_path,
        run_name="run",
        jobs=jobs,
        group_level="well",
    )

    assert (tmp_path / "Plate1" / "A01_run_run.log").read_text() == "a\n"
    assert (tmp_path / "Plate2" / "B01_run_run.log").read_text() == "b\n"


def test_results_to_log_without_jobs_falls_back_to_generic_names(tmp_path):
    """Backwards-compat path for callers that invoke results_to_log directly."""
    results = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"x\n")
    ]

    results_to_log(results=results, log_dir=tmp_path, run_name="run")

    assert (tmp_path / "process_0_run_run.log").read_text() == "x\n"


def test_results_to_log_decodes_string_stderr(tmp_path):
    """Guards against assuming stderr is always bytes (e.g. text=True callers)."""
    jobs = [_JobSpec(name="Plate1", plate_name="Plate1", command=[])]
    results = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="ok\n")
    ]

    results_to_log(results=results, log_dir=tmp_path, run_name="run", jobs=jobs)

    assert (tmp_path / "Plate1_run_run.log").read_text() == "ok\n"
