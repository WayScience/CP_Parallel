"""Unit tests for cp_parallel._build_command and its validation helpers."""

import pytest

from cp_parallel.cp_parallel import _build_command
from cp_parallel.exceptions import PlateInfoError


def test_images_directory_command(pipeline_file, images_dir, output_dir):
    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert command[0] == "cellprofiler"
    assert "-i" in command and command[command.index("-i") + 1] == str(images_dir)
    assert "--data-file" not in command
    assert output_dir.is_dir()  # created even though CellProfiler never ran


def test_loaddata_csv_command(pipeline_file, loaddata_csv, output_dir):
    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_loaddata": loaddata_csv,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert "--data-file" in command
    assert command[command.index("--data-file") + 1] == str(loaddata_csv)
    assert "-i" not in command


@pytest.mark.parametrize(
    "info_overrides",
    [
        {},  # neither path_to_images nor path_to_loaddata
    ],
)
def test_requires_exactly_one_input_source(pipeline_file, output_dir, info_overrides):
    info = {
        "path_to_pipeline": pipeline_file,
        "path_to_output": output_dir,
        **info_overrides,
    }
    with pytest.raises(PlateInfoError):
        _build_command(
            name="Plate1",
            info=info,
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_both_input_sources_rejected(
    pipeline_file, images_dir, loaddata_csv, output_dir
):
    with pytest.raises(PlateInfoError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": pipeline_file,
                "path_to_images": images_dir,
                "path_to_loaddata": loaddata_csv,
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_missing_pipeline_raises(tmp_path, images_dir, output_dir):
    with pytest.raises(FileNotFoundError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": tmp_path / "missing.cppipe",
                "path_to_images": images_dir,
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_missing_images_directory_raises(pipeline_file, tmp_path, output_dir):
    with pytest.raises(FileNotFoundError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": pipeline_file,
                "path_to_images": tmp_path / "does_not_exist",
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_missing_loaddata_file_raises(pipeline_file, tmp_path, output_dir):
    with pytest.raises(FileNotFoundError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": pipeline_file,
                "path_to_loaddata": tmp_path / "missing.csv",
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_well_level_adds_grouping_flag(pipeline_file, images_dir, output_dir):
    command = _build_command(
        name="A01",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
            "plate_name": "Plate1",
        },
        group_level="well",
        plugins_dir=None,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert "-g" in command
    assert command[command.index("-g") + 1] == "Well=A01"


def test_first_last_image_set_flags(pipeline_file, loaddata_csv, output_dir):
    command = _build_command(
        name="timepoint_0001",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_loaddata": loaddata_csv,
            "path_to_output": output_dir,
            "first_image_set": 1,
            "last_image_set": 50,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert command[command.index("-f") + 1] == "1"
    assert command[command.index("-l") + 1] == "50"


def test_conserve_memory_flag(pipeline_file, images_dir, output_dir):
    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=None,
        conserve_memory=True,
    )

    assert command[command.index("--conserve-memory") + 1] == "True"


def test_global_plugins_dir_is_applied(pipeline_file, images_dir, output_dir, tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=plugins_dir,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert command[command.index("--plugins-directory") + 1] == str(plugins_dir)


def test_per_plate_plugins_dir_overrides_global(
    pipeline_file, images_dir, output_dir, tmp_path
):
    global_plugins_dir = tmp_path / "global_plugins"
    global_plugins_dir.mkdir()
    override_plugins_dir = tmp_path / "override_plugins"
    override_plugins_dir.mkdir()

    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
            "plugins_directory": override_plugins_dir,
        },
        group_level="plate",
        plugins_dir=global_plugins_dir,
        run_with_apptainer=None,
        conserve_memory=False,
    )

    assert command[command.index("--plugins-directory") + 1] == str(
        override_plugins_dir
    )


def test_missing_plugins_dir_raises(pipeline_file, images_dir, output_dir, tmp_path):
    with pytest.raises(FileNotFoundError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": pipeline_file,
                "path_to_images": images_dir,
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=tmp_path / "does_not_exist",
            run_with_apptainer=None,
            conserve_memory=False,
        )


def test_apptainer_wraps_command(
    pipeline_file, images_dir, output_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "cp_parallel.cp_parallel.shutil.which",
        lambda runtime: "/usr/bin/apptainer" if runtime == "apptainer" else None,
    )
    sif_image = tmp_path / "cellprofiler.sif"

    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=sif_image,
        conserve_memory=False,
    )

    assert command[:3] == ["apptainer", "exec", str(sif_image)]
    assert "cellprofiler" in command


def test_apptainer_falls_back_to_singularity(
    pipeline_file, images_dir, output_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "cp_parallel.cp_parallel.shutil.which",
        lambda runtime: "/usr/bin/singularity" if runtime == "singularity" else None,
    )
    sif_image = tmp_path / "cellprofiler.sif"

    command = _build_command(
        name="Plate1",
        info={
            "path_to_pipeline": pipeline_file,
            "path_to_images": images_dir,
            "path_to_output": output_dir,
        },
        group_level="plate",
        plugins_dir=None,
        run_with_apptainer=sif_image,
        conserve_memory=False,
    )

    assert command[0] == "singularity"


def test_apptainer_raises_without_runtime(
    pipeline_file, images_dir, output_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr("cp_parallel.cp_parallel.shutil.which", lambda runtime: None)

    with pytest.raises(EnvironmentError):
        _build_command(
            name="Plate1",
            info={
                "path_to_pipeline": pipeline_file,
                "path_to_images": images_dir,
                "path_to_output": output_dir,
            },
            group_level="plate",
            plugins_dir=None,
            run_with_apptainer=tmp_path / "cellprofiler.sif",
            conserve_memory=False,
        )
