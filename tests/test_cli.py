"""CLI: flag parsing + threading the request through main to the transport."""

from __future__ import annotations

import pytest

from synthetic_portraits import cli
from synthetic_portraits.faces import FakeFaceDetector
from synthetic_portraits.transport import FakeComfyClient

_ACCEPT = FakeFaceDetector([1])  # every render passes the face check on the first attempt


def test_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "prompt" in capsys.readouterr().out.lower()


def test_generate_entry_point_delegates_to_cli_main():
    import generate

    assert generate.main is cli.main


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


def test_main_defaults_to_portrait_832x1216(tmp_path):
    fake = FakeComfyClient()

    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)

    latent = next(
        n for n in fake.queued_workflows[0].values() if n["class_type"] == "EmptyLatentImage"
    )
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (832, 1216)


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


def test_main_defaults_to_a_single_image(tmp_path):
    fake = FakeComfyClient()
    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)
    assert len(fake.queued_workflows) == 1


def test_main_rejects_unknown_model(tmp_path):
    argv = ["--prompt", "p", "--model", "nope", "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv, transport=FakeComfyClient(), detector=_ACCEPT)
    assert exc.value.code != 0


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


def test_no_identity_stays_on_the_default_graph_and_uploads_nothing(tmp_path):
    fake = FakeComfyClient()

    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake, detector=_ACCEPT)

    assert fake.uploads == []
    classes = {n["class_type"] for n in fake.queued_workflows[0].values()}
    assert "ApplyInstantID" not in classes


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


def test_prompt_and_prompts_together_is_an_error(tmp_path):
    pf = _prompts_file(tmp_path, ["x"])
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--prompt", "y", "--prompts", pf, "--out", str(tmp_path)],
            transport=FakeComfyClient(),
            detector=_ACCEPT,
        )
    assert exc.value.code != 0


def test_prompts_empty_file_is_an_error(tmp_path):
    pf = _prompts_file(tmp_path, ["   ", ""])
    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["--prompts", pf, "--out", str(tmp_path)],
            transport=FakeComfyClient(),
            detector=_ACCEPT,
        )
    assert exc.value.code != 0


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
