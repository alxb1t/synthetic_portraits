"""CLI: flag parsing + threading the request through main to the transport."""

from __future__ import annotations

import http.client
import re
import signal
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from pathlib import Path

import gpunit
import pytest
from conftest import REPO_ROOT

from synthetic_portraits import cli
from synthetic_portraits.faces import FakeFaceDetector
from synthetic_portraits.transport import ComfyError, ComfyExecutionError, FakeComfyClient

_ACCEPT = FakeFaceDetector([1])  # every render passes the face check on the first attempt


@pytest.mark.spec("portrait.help-exits-zero")
def test_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "prompt" in capsys.readouterr().out.lower()


@pytest.mark.spec("portrait.entry-point")
def test_generate_entry_point_delegates_to_cli_main():
    import generate

    assert generate.main is cli.main


@pytest.mark.spec("portrait.no-prompt-prints-help")
def test_no_prompt_prints_help_and_returns_zero(capsys):
    assert cli.main([]) == 0
    assert "prompt" in capsys.readouterr().out.lower()


def _queued_positive_text(fake: FakeComfyClient) -> str:
    node = next(
        n
        for n in fake.queued_workflows[0].values()
        if n["class_type"] == "CLIPTextEncode" and "Positive" in n["_meta"]["title"]
    )
    return node["inputs"]["text"]


@pytest.mark.spec("portrait.prompt-and-seed-queued")
def test_main_threads_prompt_and_seed_through_to_the_queued_workflow(tmp_path):
    fake = FakeComfyClient()

    rc = cli.main(
        ["--prompt", "a woman with a tattoo", "--seed", "7", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    assert rc == 0
    assert _queued_positive_text(fake) == "a woman with a tattoo"
    ksampler = next(n for n in fake.queued_workflows[0].values() if n["class_type"] == "KSampler")
    assert ksampler["inputs"]["seed"] == 7


@pytest.mark.spec("portrait.default-dimensions")
def test_main_defaults_to_portrait_832x1216(tmp_path):
    fake = FakeComfyClient()

    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)

    latent = next(
        n for n in fake.queued_workflows[0].values() if n["class_type"] == "EmptyLatentImage"
    )
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (832, 1216)


@pytest.mark.spec("portrait.dimension-overrides")
def test_main_honours_width_height_overrides(tmp_path):
    fake = FakeComfyClient()

    cli.main(
        ["--prompt", "p", "--width", "768", "--height", "1152", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    latent = next(
        n for n in fake.queued_workflows[0].values() if n["class_type"] == "EmptyLatentImage"
    )
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (768, 1152)


@pytest.mark.spec("portrait.count-consecutive-seeds")
def test_main_count_renders_n_images_with_consecutive_seeds(tmp_path):
    fake = FakeComfyClient()

    rc = cli.main(
        ["--prompt", "p", "--seed", "10", "-n", "3", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    assert rc == 0
    assert len(fake.queued_workflows) == 3
    seeds = [
        next(n for n in wf.values() if n["class_type"] == "KSampler")["inputs"]["seed"]
        for wf in fake.queued_workflows
    ]
    assert seeds == [10, 11, 12]  # reproducible: seed, seed+1, seed+2


@pytest.mark.spec("portrait.count-defaults-to-one")
def test_main_defaults_to_a_single_image(tmp_path):
    fake = FakeComfyClient()
    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)
    assert len(fake.queued_workflows) == 1


@pytest.mark.spec("models.unknown-rejected")
def test_main_rejects_unknown_model(tmp_path):
    argv = ["--prompt", "p", "--model", "nope", "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv, transport=FakeComfyClient(), detector=_ACCEPT)
    assert exc.value.code != 0


@pytest.mark.spec("models.identity-graph-off-menu")
def test_main_rejects_selecting_the_internal_identity_graph_by_name(tmp_path):
    # The identity graph is auto-selected by --identity (a hero image), never chosen by name:
    # picking it without a hero queues a graph whose LoadImage still holds a placeholder, which
    # only fails at GPU time. It must not be a user-facing --model choice.
    from synthetic_portraits.models import IDENTITY_MODEL

    argv = ["--prompt", "p", "--model", IDENTITY_MODEL, "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv, transport=FakeComfyClient(), detector=_ACCEPT)
    assert exc.value.code != 0


@pytest.mark.spec("faces.cli-reports-failure")
def test_main_returns_nonzero_and_summarizes_when_a_face_check_fails(tmp_path, capsys):
    fake = FakeComfyClient()
    # Both renders never reach one face -> both exhaust their attempts.
    det = FakeFaceDetector([0])

    rc = cli.main(
        ["--prompt", "p", "-n", "2", "--out", str(tmp_path)],
        transport=fake,
        detector=det,
    )

    assert rc != 0
    err = capsys.readouterr().err
    assert "2/2" in err  # summary line: how many images were kept-but-undetected


@pytest.mark.spec("faces.cli-silent-on-success")
def test_main_all_faces_detected_returns_zero_and_no_warning(tmp_path, capsys):
    fake = FakeComfyClient()

    rc = cli.main(
        ["--prompt", "p", "-n", "2", "--out", str(tmp_path)],
        transport=fake,
        detector=FakeFaceDetector([1]),
    )

    assert rc == 0
    assert capsys.readouterr().err == ""


# --- --identity: auto-select the InstantID graph + upload the hero ----------


def _hero(tmp_path) -> str:
    p = tmp_path / "alice.png"
    p.write_bytes(b"HEROBYTES")
    return str(p)


@pytest.mark.spec("identity.selects-graph-and-uploads")
def test_identity_selects_the_instantid_graph_and_uploads_the_hero(tmp_path):
    fake = FakeComfyClient()
    hero = _hero(tmp_path)

    rc = cli.main(
        ["--prompt", "same person, cafe", "--identity", hero, "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    assert rc == 0
    # The hero is uploaded once, by its filename.
    assert fake.uploads == [("alice.png", b"HEROBYTES")]
    # The identity graph was used: it carries an ApplyInstantID node.
    classes = {n["class_type"] for n in fake.queued_workflows[0].values()}
    assert "ApplyInstantID" in classes
    # ...and the hero LoadImage points at the uploaded name.
    load = next(n for n in fake.queued_workflows[0].values() if n["class_type"] == "LoadImage")
    assert load["inputs"]["image"] == "alice.png"


@pytest.mark.spec("identity.no-hero-no-upload")
def test_no_identity_stays_on_the_default_graph_and_uploads_nothing(tmp_path):
    fake = FakeComfyClient()

    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)

    assert fake.uploads == []
    classes = {n["class_type"] for n in fake.queued_workflows[0].values()}
    assert "ApplyInstantID" not in classes


@pytest.mark.spec("identity.missing-hero-is-an-error")
def test_identity_with_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--prompt", "p", "--identity", str(tmp_path / "nope.png"), "--out", str(tmp_path)],
            transport=FakeComfyClient(),
            detector=_ACCEPT,
        )
    assert exc.value.code != 0


# --- --prompts: character-sheet / batch over the selected path --------------


def _prompts_file(tmp_path, lines) -> str:
    f = tmp_path / "prompts.txt"
    f.write_text("\n".join(lines) + "\n")
    return str(f)


def _positive_texts(fake: FakeComfyClient) -> list[str]:
    texts = []
    for wf in fake.queued_workflows:
        node = next(
            n
            for n in wf.values()
            if n["class_type"] == "CLIPTextEncode" and "Positive" in n["_meta"]["title"]
        )
        texts.append(node["inputs"]["text"])
    return texts


@pytest.mark.spec("batch.independent-people")
@pytest.mark.spec("batch.stable-filenames")
def test_prompts_alone_is_a_batch_of_independent_people(tmp_path):
    fake = FakeComfyClient()
    pf = _prompts_file(tmp_path, ["a woman in a park", "a man at a cafe"])

    rc = cli.main(
        ["--prompts", pf, "--seed", "0", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    assert rc == 0
    # One render per line, on the default graph, uploading nothing.
    assert _positive_texts(fake) == ["a woman in a park", "a man at a cafe"]
    assert fake.uploads == []
    # A labeled set: one stable-named file per prompt.
    names = sorted(p.name for p in tmp_path.glob("*.png"))
    assert names == ["00_00_a_woman_in_a_park.png", "01_00_a_man_at_a_cafe.png"]


@pytest.mark.spec("batch.identity-character-sheet")
def test_prompts_with_identity_is_a_same_person_character_sheet(tmp_path):
    fake = FakeComfyClient()
    hero = _hero(tmp_path)
    pf = _prompts_file(tmp_path, ["sitting at a cafe", "standing in a park"])

    rc = cli.main(
        ["--prompts", pf, "--identity", hero, "--seed", "0", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    assert rc == 0
    # Every render uses the identity graph and the same hero.
    for wf in fake.queued_workflows:
        assert "ApplyInstantID" in {n["class_type"] for n in wf.values()}
    assert ("alice.png", b"HEROBYTES") in fake.uploads
    assert _positive_texts(fake) == ["sitting at a cafe", "standing in a park"]


@pytest.mark.spec("batch.count-multiplies")
def test_prompts_multiplies_with_count(tmp_path):
    fake = FakeComfyClient()
    pf = _prompts_file(tmp_path, ["one", "two"])

    cli.main(
        ["--prompts", pf, "-n", "2", "--seed", "0", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    # P prompts x N each = 4 renders, with distinct labeled files.
    assert len(fake.queued_workflows) == 4
    names = sorted(p.name for p in tmp_path.glob("*.png"))
    assert names == [
        "00_00_one.png",
        "00_01_one.png",
        "01_00_two.png",
        "01_01_two.png",
    ]


@pytest.mark.spec("batch.seeds-distinct-deterministic")
def test_prompts_seeds_are_deterministic_and_distinct(tmp_path):
    fake = FakeComfyClient()
    pf = _prompts_file(tmp_path, ["one", "two"])

    cli.main(
        ["--prompts", pf, "-n", "2", "--seed", "100", "--out", str(tmp_path)],
        transport=fake,
        detector=_ACCEPT,
    )

    seeds = [
        next(n for n in wf.values() if n["class_type"] == "KSampler")["inputs"]["seed"]
        for wf in fake.queued_workflows
    ]
    assert seeds == [100, 101, 102, 103]  # base_seed + running index, reproducible


@pytest.mark.spec("batch.sources-are-exclusive")
def test_prompt_and_prompts_together_is_an_error(tmp_path):
    pf = _prompts_file(tmp_path, ["x"])
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--prompt", "y", "--prompts", pf, "--out", str(tmp_path)],
            transport=FakeComfyClient(),
            detector=_ACCEPT,
        )
    assert exc.value.code != 0


@pytest.mark.spec("batch.empty-file-is-an-error")
def test_prompts_empty_file_is_an_error(tmp_path):
    pf = _prompts_file(tmp_path, ["   ", ""])
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--prompts", pf, "--out", str(tmp_path)],
            transport=FakeComfyClient(),
            detector=_ACCEPT,
        )
    assert exc.value.code != 0


@pytest.mark.spec("portrait.random-seed-consistent-within-run")
def test_omitting_seed_still_renders_reproducibly_within_a_run(tmp_path):
    # No --seed -> a random base seed is chosen once; the set stays internally consistent
    # (distinct, consecutive seeds) even though the base is not fixed across runs.
    fake = FakeComfyClient()
    pf = _prompts_file(tmp_path, ["one", "two", "three"])

    cli.main(["--prompts", pf, "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)

    seeds = [
        next(n for n in wf.values() if n["class_type"] == "KSampler")["inputs"]["seed"]
        for wf in fake.queued_workflows
    ]
    assert seeds == [seeds[0], seeds[0] + 1, seeds[0] + 2]


# --- The `faces` group, reported early (change 0004, design D5) --------------


@pytest.mark.spec("faces.cli-missing-dep-named")
def test_missing_faces_group_names_the_group_not_the_transitive_module(
    monkeypatch, tmp_path, capsys
):
    # The bare failure is `ModuleNotFoundError: No module named 'cv2'`, which names a
    # transitive module and tells the operator nothing about how to fix it.
    monkeypatch.setattr(cli, "missing_face_dependencies", lambda: ["cv2"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=FakeComfyClient())

    assert excinfo.value.code != 0
    message = capsys.readouterr().err
    assert "faces" in message
    assert "--group faces" in message
    assert "cv2" in message, "the missing module is still worth naming, as a detail"


@pytest.mark.spec("faces.cli-missing-dep-early")
def test_missing_faces_group_submits_nothing_to_the_transport(monkeypatch, tmp_path):
    # The point of the check: the render server is a metered GPU pod, so the operator must
    # learn the dependency is missing while it is still free to fix. Nothing may be queued.
    monkeypatch.setattr(cli, "missing_face_dependencies", lambda: ["cv2"])
    fake = FakeComfyClient()

    with pytest.raises(SystemExit):
        cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake)

    assert fake.queued_workflows == []
    assert fake.uploads == []


@pytest.mark.spec("faces.cli-injected-detector-skips-check")
def test_an_injected_detector_never_consults_the_optional_group(monkeypatch, tmp_path):
    # Keeps the seam intact: every test injects a stand-in, so the suite must never need
    # the optional group. A checker that raises proves it was not consulted at all.
    def _must_not_be_called():
        raise AssertionError("the dependency check ran despite an injected detector")

    monkeypatch.setattr(cli, "missing_face_dependencies", _must_not_be_called)

    exit_code = cli.main(
        ["--prompt", "p", "--out", str(tmp_path)],
        transport=FakeComfyClient(),
        detector=_ACCEPT,
    )

    assert exit_code == 0


# --- --pod: one gpunit session around the batch (change 0006, design D1-D3) ----------

_IMAGE = "ghcr.io/alxb1t/synthetic_portraits@sha256:" + "a" * 64
_LOCAL_PORT = 18188


class _FakeSession:
    """Stand in for gpunit's open session: an image, and one forwarded port."""

    image = _IMAGE

    def __init__(self):
        self.ports: list[int] = []

    def port(self, remote: int) -> int:
        self.ports.append(remote)
        return _LOCAL_PORT


class _FakeOpener:
    """Stand in for `gpu.open_session`: yield a session, record its open and its close."""

    def __init__(self, *, on_open: BaseException | None = None, on_close: Exception | None = None):
        self.on_open = on_open
        self.on_close = on_close
        self.opened: list[tuple[Path, dict[str, str]]] = []
        self.closed = False
        self.session = _FakeSession()

    def __call__(self, root, environ, say):
        self.opened.append((root, dict(environ)))
        return self._block()

    @contextmanager
    def _block(self):
        if self.on_open is not None:
            raise self.on_open
        try:
            yield self.session
        finally:
            self.closed = True
            if self.on_close is not None:
                raise self.on_close


class _Ordered(FakeComfyClient):
    """A fake server that logs each call by kind, so their order can be asserted."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls: list[str] = []

    def system_stats(self):
        self.calls.append("stats")
        return super().system_stats()

    def queue_prompt(self, workflow):
        self.calls.append("queue")
        return super().queue_prompt(workflow)


class _Interrupting(FakeComfyClient):
    """A fake server whose first report is cut by the signal gpunit raises on SIGTERM."""

    def system_stats(self):
        raise gpunit.Interrupted(signal.SIGTERM)


def _on_pod(tmp_path, opener, client, argv=()):
    urls: list[str] = []

    def connect(url):
        urls.append(url)
        return client

    rc = cli.main(
        ["--pod", "--prompt", "p", "--out", str(tmp_path), *argv],
        detector=_ACCEPT,
        open_session=opener,
        connect=connect,
    )
    return rc, urls


@pytest.fixture
def quick_wait(monkeypatch):
    monkeypatch.setattr(cli, "WAIT_S", 0.0)
    monkeypatch.setattr(cli, "POLL_S", 0.0)


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_render_that_raises_still_closes_the_session(tmp_path):
    opener = _FakeOpener()

    with pytest.raises(ComfyExecutionError):
        _on_pod(tmp_path, opener, FakeComfyClient(queue_error="boom"))

    assert opener.closed


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_server_that_never_answers_refuses_and_closes_the_session(tmp_path, quick_wait, capsys):
    opener = _FakeOpener()
    client = FakeComfyClient(silent_stats=10**6)

    rc, _ = _on_pod(tmp_path, opener, client)

    assert rc == 1
    assert opener.closed
    assert client.queued_workflows == []
    assert "refused: the render server did not answer within 0s" in capsys.readouterr().err


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_signal_inside_the_session_closes_it_and_exits_128_plus_the_signal(tmp_path):
    opener = _FakeOpener()

    rc, _ = _on_pod(tmp_path, opener, _Interrupting())

    assert rc == 128 + signal.SIGTERM
    assert opener.closed


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_lost_create_exits_3_naming_the_teardown_that_reads_the_key(tmp_path, capsys):
    rc, _ = _on_pod(tmp_path, _FakeOpener(on_open=gpunit.Lost()), FakeComfyClient())

    assert rc == 3
    assert "uv run --env-file .env gpunit down" in capsys.readouterr().err


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_failed_teardown_exits_1_naming_the_teardown_that_reads_the_key(tmp_path, capsys):
    opener = _FakeOpener(on_close=gpunit.TeardownFailed("the teardown failed"))

    rc, _ = _on_pod(tmp_path, opener, FakeComfyClient())

    assert rc == 1
    assert "uv run --env-file .env gpunit down" in capsys.readouterr().err


@pytest.mark.spec("pod.session-closes-on-every-exit")
def test_a_refused_session_exits_1_and_renders_nothing(tmp_path):
    client = FakeComfyClient()

    rc, _ = _on_pod(tmp_path, _FakeOpener(on_open=gpunit.Refused("no card")), client)

    assert rc == 1
    assert client.queued_workflows == []


@pytest.mark.spec("pod.session-awaits-the-server")
def test_the_server_is_asked_through_the_forwarded_port_before_any_render(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "POLL_S", 0.0)
    opener = _FakeOpener()
    client = _Ordered(silent_stats=2)

    rc, urls = _on_pod(tmp_path, opener, client)

    assert rc == 0
    assert opener.session.ports == [8188]
    assert urls == [f"http://127.0.0.1:{_LOCAL_PORT}"]
    assert client.calls == ["stats", "stats", "stats", "queue"]


class _Clock:
    """A clock that moves only when slept on, so a 900 s wait costs no wall time."""

    def __init__(self):
        self.now = 0.0
        self.asked_at: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def silent(self) -> None:
        self.asked_at.append(self.now)
        raise ComfyError("cannot reach ComfyUI: connection refused")


@pytest.mark.spec("pod.session-awaits-the-server")
def test_the_wait_gives_up_after_900_seconds_with_no_answer():
    clock = _Clock()

    assert not cli.await_server(clock.silent, sleep=clock.sleep, clock=lambda: clock.now)

    assert clock.asked_at[-1] == 900.0
    assert clock.asked_at[:3] == [0.0, 5.0, 10.0]


@pytest.mark.spec("pod.session-awaits-the-server")
@pytest.mark.parametrize(
    "silence",
    [ComfyError("refused"), ConnectionResetError(), http.client.RemoteDisconnected("cut")],
    ids=["unreachable", "reset", "cut-by-the-tunnel"],
)
def test_the_wait_asks_again_while_the_tunnel_has_no_server_behind_it(silence):
    answers = iter([silence])

    def ask():
        fault = next(answers, None)
        if fault is not None:
            raise fault

    assert cli.await_server(ask, sleep=lambda _: None)


@pytest.mark.spec("pod.session-names-its-image")
def test_the_session_prints_the_image_it_booted(tmp_path, capsys):
    _on_pod(tmp_path, _FakeOpener(), FakeComfyClient())

    assert f"session image: {_IMAGE}" in capsys.readouterr().err.splitlines()


@pytest.mark.spec("pod.session-reads-env-whole")
def test_the_key_in_dot_env_reaches_the_session_over_the_process_environment(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('# the key\nRUNPOD_API_KEY="from-dot-env"\n')
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setenv("SP_TEST_PROCESS_ONLY", "kept")
    monkeypatch.setattr(cli, "REPOSITORY", tmp_path)
    opener = _FakeOpener()

    _on_pod(tmp_path / "out", opener, FakeComfyClient())

    [(root, environ)] = opener.opened
    assert root == tmp_path
    assert environ["RUNPOD_API_KEY"] == "from-dot-env"
    assert environ["SP_TEST_PROCESS_ONLY"] == "kept"


def _provider_names(root: Path) -> list[str]:
    """Return each Python file under `root` that names a provider variable."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "RUNPOD_" in path.read_text()
    )


@pytest.mark.spec("pod.session-reads-env-whole")
def test_the_runtime_code_names_no_provider_variable():
    assert _provider_names(REPO_ROOT / "synthetic_portraits") == []
    assert "RUNPOD_" not in (REPO_ROOT / "generate.py").read_text()


@pytest.mark.spec_exempt("structural: twin of test_the_runtime_code_names_no_provider_variable")
def test_the_provider_check_catches_a_module_naming_the_key(tmp_path):
    (tmp_path / "ok.py").write_text("import os\n")
    (tmp_path / "leak.py").write_text('KEY = os.environ["RUNPOD_API_KEY"]\n')

    assert _provider_names(tmp_path) == ["leak.py"]


@pytest.mark.spec("faces.cli-missing-dep-early")
def test_a_missing_faces_group_opens_no_session(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "missing_face_dependencies", lambda: ["cv2"])
    opener = _FakeOpener()

    with pytest.raises(SystemExit):
        cli.main(["--pod", "--prompt", "p", "--out", str(tmp_path)], open_session=opener)

    assert opener.opened == []


@pytest.mark.spec_exempt("structural: --pod and --server name one render server (0006 D1)")
def test_pod_and_server_together_is_an_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--pod", "--server", "http://x:8188", "--prompt", "p", "--out", str(tmp_path)],
            detector=_ACCEPT,
            open_session=_FakeOpener(),
        )
    assert exc.value.code != 0


@pytest.mark.spec_exempt("structural: one port, declared in gpunit.toml and here")
def test_the_port_the_cli_reads_is_the_one_gpunit_toml_forwards():
    spec = tomllib.loads((REPO_ROOT / "gpunit.toml").read_text())
    assert spec["ports"] == [cli.POD_PORT]


def _gpunit_importers(package: Path) -> list[str]:
    """Return each module under `package` but `gpu.py` that imports gpunit."""
    return sorted(
        path.name
        for path in package.glob("*.py")
        if path.name != "gpu.py"
        and re.search(r"^\s*(import gpunit|from gpunit\b)", path.read_text(), re.M)
    )


@pytest.mark.spec_exempt("structural: gpunit is reached only through gpu.py (0006 D2)")
def test_only_gpu_py_imports_gpunit():
    assert _gpunit_importers(REPO_ROOT / "synthetic_portraits") == []
    code = "import sys, synthetic_portraits.cli; print('gpunit' in sys.modules)"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    assert proc.stdout.strip() == "False"


@pytest.mark.spec_exempt("structural: twin of test_only_gpu_py_imports_gpunit")
def test_the_import_check_catches_a_second_module_importing_gpunit(tmp_path):
    (tmp_path / "gpu.py").write_text("def f():\n    import gpunit\n")
    (tmp_path / "cli.py").write_text("from gpunit import Lost\n")

    assert _gpunit_importers(tmp_path) == ["cli.py"]
