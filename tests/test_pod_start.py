"""The pod's start module: the models mapped onto the volume, provisioned, then ComfyUI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from synthetic_portraits import pod_start


class _Pod:
    """A pod's tree under `tmp_path`, with the provisioner and the server faked."""

    def __init__(self, tmp_path: Path, *, fetch_exit: int = 0):
        self.comfyui = tmp_path / "ComfyUI"
        self.comfyui.mkdir()
        self.volume = tmp_path / "volume"
        self.volume.mkdir()
        self.fetch_exit = fetch_exit
        self.events: list[str] = []
        self.fetched: list[list[str]] = []

    def run(self, command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        self.events.append("fetch")
        self.fetched.append(command)
        return subprocess.CompletedProcess(command, self.fetch_exit)

    def serve(self, comfyui: Path) -> None:
        self.events.append("serve")

    def start(self, env: dict[str, str] | None = None) -> int:
        return pod_start.main(
            {"GPUNIT_VOLUME_PATH": str(self.volume)} if env is None else env,
            comfyui=self.comfyui,
            run=self.run,
            serve=self.serve,
        )


@pytest.mark.spec("pod.start-maps-model-dirs")
def test_every_model_directory_resolves_onto_the_volume(tmp_path):
    pod = _Pod(tmp_path)

    assert pod.start() == 0

    models = pod.volume / "models"
    paths = (pod.comfyui / "extra_model_paths.yaml").read_text()
    assert f"base_path: {models}" in paths
    for folder in ("checkpoints", "controlnet", "instantid", "ultralytics", "insightface"):
        assert f"  {folder}: {folder}\n" in paths, folder


@pytest.mark.spec("pod.start-maps-model-dirs")
def test_the_folders_the_extensions_hard_code_are_linked_onto_the_volume(tmp_path):
    pod = _Pod(tmp_path)
    # The image's own tree may already hold one of them as a plain directory.
    (pod.comfyui / "models" / "ultralytics").mkdir(parents=True)

    pod.start()

    for folder in ("ultralytics", "insightface"):
        link = pod.comfyui / "models" / folder
        assert link.is_symlink(), folder
        assert link.resolve() == (pod.volume / "models" / folder).resolve()


@pytest.mark.spec("pod.start-maps-model-dirs")
def test_the_models_are_provisioned_onto_the_volume_before_the_server_starts(tmp_path):
    pod = _Pod(tmp_path)

    pod.start()

    assert pod.events == ["fetch", "serve"]
    [command] = pod.fetched
    assert command[command.index("--models-dir") + 1] == str(pod.volume / "models")
    assert command[1:3] == [str(pod_start.PROVISION), "fetch"]


@pytest.mark.spec("pod.start-stops-on-a-failed-provision")
def test_a_failed_provision_exits_1_and_starts_no_server(tmp_path):
    pod = _Pod(tmp_path, fetch_exit=1)

    assert pod.start() == 1
    assert pod.events == ["fetch"]


@pytest.mark.spec("pod.start-stops-on-a-failed-provision")
def test_a_pod_told_no_volume_exits_1_and_provisions_nothing(tmp_path, capsys):
    pod = _Pod(tmp_path)

    assert pod.start(env={}) == 1
    assert pod.events == []
    assert "GPUNIT_VOLUME_PATH" in capsys.readouterr().err


@pytest.mark.spec_exempt("structural: every step says when it began")
def test_each_step_prints_its_utc_start(tmp_path, capsys):
    _Pod(tmp_path).start()

    steps = [line for line in capsys.readouterr().out.splitlines() if " step: " in line]
    assert [line.split(" step: ")[1] for line in steps] == [
        "the volume",
        "the model paths",
        "provisioning",
        "ComfyUI",
    ]
    assert all(line[:20].endswith("Z") and line[10] == "T" for line in steps)
