"""Shared fixtures for cp_parallel tests."""

import pathlib
import subprocess

import pytest


@pytest.fixture
def pipeline_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "analysis.cppipe"
    path.write_text("CellProfiler Pipeline: http://www.cellprofiler.org\n")
    return path


@pytest.fixture
def images_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "images"
    path.mkdir()
    (path / "well_A01_z01.tif").write_bytes(b"")
    return path


@pytest.fixture
def loaddata_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "load_data.csv"
    path.write_text("Metadata_Plate,Metadata_Well\nPlate1,A01\n")
    return path


@pytest.fixture
def output_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "output"


@pytest.fixture
def log_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "logs"


def make_completed_process(
    args, returncode: int = 0, stderr: bytes = b"CellProfiler run complete.\n"
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=b"", stderr=stderr
    )
