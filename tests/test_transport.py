"""Transport seam: the ComfyUI /prompt -> poll /history -> /view contract.

Every ComfyUI call goes through the ``ComfyTransport`` Protocol. ``FakeComfyClient``
replays the poll state machine in-memory (no GPU, no network); ``ComfyClient`` is the
real stdlib-``urllib`` implementation, exercised here against a stubbed ``urlopen``.
"""

from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from synthetic_portraits.transport import (
    ComfyClient,
    ComfyExecutionError,
    ComfyTimeoutError,
    ComfyTransport,
    FakeComfyClient,
    await_outputs,
)

# A no-op sleep so the poll loop never actually waits in tests.
NO_SLEEP = lambda _seconds: None  # noqa: E731


# --- Protocol conformance ---------------------------------------------------


@pytest.mark.spec("comfy.seam-is-substitutable")
def test_fake_and_real_clients_satisfy_the_transport_protocol():
    assert isinstance(FakeComfyClient(), ComfyTransport)
    assert isinstance(ComfyClient("http://localhost:8188"), ComfyTransport)


# --- FakeComfyClient records the full call sequence -------------------------


@pytest.mark.spec("comfy.fake-replays-state-machine")
def test_fake_client_records_upload_queue_and_view(txt2img_workflow):
    fake = FakeComfyClient()

    uploaded = fake.upload_image("pose.png", b"\x89PNG-bytes")
    prompt_id = fake.queue_prompt(txt2img_workflow)
    fake.get_image("out.png", "", "output")

    assert fake.uploads == [("pose.png", b"\x89PNG-bytes")]
    assert uploaded == "pose.png"
    assert fake.queued_workflows == [txt2img_workflow]
    assert isinstance(prompt_id, str) and prompt_id
    assert fake.requested_views == [("out.png", "", "output")]


# --- The poll state machine (await_outputs) ---------------------------------


@pytest.mark.spec("comfy.polls-until-done")
def test_await_outputs_polls_until_history_is_populated():
    # Pending for two polls, then the outputs appear on the third.
    fake = FakeComfyClient(polls_until_done=3)

    outputs = await_outputs(fake, "fake-prompt", interval=0, sleep=NO_SLEEP)

    assert fake.poll_count == 3
    assert "9" in outputs  # SaveImage node's output bucket
    assert outputs["9"]["images"][0]["filename"].endswith(".png")


@pytest.mark.spec("comfy.returns-immediately-when-done")
def test_await_outputs_returns_immediately_when_already_done():
    fake = FakeComfyClient(polls_until_done=1)

    outputs = await_outputs(fake, "fake-prompt", interval=0, sleep=NO_SLEEP)

    assert fake.poll_count == 1
    assert outputs


@pytest.mark.spec("comfy.execution-error-surfaced")
def test_await_outputs_raises_on_server_execution_error():
    fake = FakeComfyClient(polls_until_done=1, execution_error="KSampler: OOM")

    with pytest.raises(ComfyExecutionError, match="OOM"):
        await_outputs(fake, "fake-prompt", interval=0, sleep=NO_SLEEP)


@pytest.mark.spec("comfy.timeout")
def test_await_outputs_times_out_when_never_completing():
    # Completion would need 99 polls; we cap at 3.
    fake = FakeComfyClient(polls_until_done=99)

    with pytest.raises(ComfyTimeoutError):
        await_outputs(fake, "fake-prompt", max_polls=3, interval=0, sleep=NO_SLEEP)

    assert fake.poll_count == 3


@pytest.mark.spec("comfy.queue-rejection-is-an-error")
def test_queue_prompt_error_is_surfaced_by_the_fake():
    fake = FakeComfyClient(queue_error="invalid prompt: node 6 missing input")

    with pytest.raises(ComfyExecutionError, match="node 6"):
        fake.queue_prompt({"anything": True})


# --- ComfyClient: real urllib impl against a stubbed urlopen ----------------


def _stub_urlopen(monkeypatch, handler):
    """Route ``urllib.request.urlopen`` through ``handler(req) -> bytes``.

    ``io.BytesIO`` is already a context manager exposing ``.read()`` — exactly the slice
    of the HTTP response object that :class:`ComfyClient` uses.
    """
    monkeypatch.setattr(
        "synthetic_portraits.transport.urlopen",
        lambda req, timeout=None: io.BytesIO(handler(req)),
    )


@pytest.mark.spec("comfy.queue-posts-and-returns-id")
def test_comfy_client_queue_prompt_posts_prompt_and_returns_id(monkeypatch, txt2img_workflow):
    captured = {}

    def handler(req):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return json.dumps({"prompt_id": "srv-123", "number": 1}).encode()

    _stub_urlopen(monkeypatch, handler)
    client = ComfyClient("http://localhost:8188", client_id="cid-1")

    prompt_id = client.queue_prompt(txt2img_workflow)

    assert prompt_id == "srv-123"
    assert captured["url"].endswith("/prompt")
    assert captured["body"]["prompt"] == txt2img_workflow
    assert captured["body"]["client_id"] == "cid-1"


@pytest.mark.spec("comfy.queue-rejection-is-an-error")
def test_comfy_client_queue_prompt_raises_on_http_validation_error(monkeypatch, txt2img_workflow):
    def handler(req):
        raise HTTPError(
            req.full_url,
            400,
            "Bad Request",
            hdrs=Message(),
            fp=io.BytesIO(b'{"error": "invalid prompt", "node_errors": {"6": "x"}}'),
        )

    _stub_urlopen(monkeypatch, handler)
    client = ComfyClient("http://localhost:8188")

    with pytest.raises(ComfyExecutionError, match="invalid prompt"):
        client.queue_prompt(txt2img_workflow)


@pytest.mark.spec("comfy.history-parsed")
def test_comfy_client_get_history_parses_json(monkeypatch):
    payload = {"srv-123": {"outputs": {"9": {"images": []}}, "status": {"status_str": "success"}}}
    _stub_urlopen(monkeypatch, lambda req: json.dumps(payload).encode())
    client = ComfyClient("http://localhost:8188")

    assert client.get_history("srv-123") == payload


@pytest.mark.spec("comfy.view-returns-bytes")
def test_comfy_client_get_image_returns_raw_bytes(monkeypatch):
    captured = {}

    def handler(req):
        captured["url"] = req.full_url
        return b"\x89PNG\r\n\x1a\n"

    _stub_urlopen(monkeypatch, handler)
    client = ComfyClient("http://localhost:8188")

    data = client.get_image("out.png", "sub", "output")

    assert data == b"\x89PNG\r\n\x1a\n"
    assert "filename=out.png" in captured["url"]
    assert "subfolder=sub" in captured["url"]
    assert "type=output" in captured["url"]


@pytest.mark.spec("comfy.upload-multipart")
def test_comfy_client_upload_image_sends_multipart(monkeypatch):
    captured = {}

    def handler(req):
        captured["content_type"] = req.headers.get("Content-type", "")
        captured["body"] = req.data
        return json.dumps({"name": "pose.png", "subfolder": "", "type": "input"}).encode()

    _stub_urlopen(monkeypatch, handler)
    client = ComfyClient("http://localhost:8188")

    name = client.upload_image("pose.png", b"IMG")

    assert name == "pose.png"
    assert captured["content_type"].startswith("multipart/form-data; boundary=")
    assert b'filename="pose.png"' in captured["body"]
    assert b"IMG" in captured["body"]


# --- The explicit User-Agent (change 0004, design D4) ------------------------


def _capture_request(monkeypatch, call):
    """Run ``call(client)`` against a stubbed ``urlopen``; return the ``Request`` it built."""
    captured = {}

    def handler(req):
        captured["req"] = req
        # Serves every call path: `.get("name")` and `.get("prompt_id")` both resolve,
        # and `get_image` reads the raw bytes without decoding them.
        return json.dumps({"name": "pose.png", "prompt_id": "abc"}).encode()

    _stub_urlopen(monkeypatch, handler)
    call(ComfyClient("http://localhost:8188"))
    return captured["req"]


CALLS = {
    "queue_prompt": lambda c: c.queue_prompt({"1": {"class_type": "KSampler"}}),
    "get_history": lambda c: c.get_history("abc"),
    "get_image": lambda c: c.get_image("out.png", "", "output"),
    "upload_image": lambda c: c.upload_image("pose.png", b"IMG"),
}


@pytest.mark.parametrize("call_name", list(CALLS))
@pytest.mark.spec("comfy.sends-user-agent")
def test_every_request_carries_an_explicit_user_agent(monkeypatch, call_name):
    # Cloudflare answers `Python-urllib/3.x` with error 1010 — a user-agent block — so a
    # request left on the stdlib default is refused before it reaches ComfyUI. Every call
    # path must set one, which is why this is parametrized across all four rather than
    # asserted on whichever one happens to be convenient.
    req = _capture_request(monkeypatch, CALLS[call_name])

    user_agent = req.get_header("User-agent")

    assert user_agent, f"{call_name} left the User-Agent to the standard library's default"
    assert not user_agent.startswith("Python-urllib"), user_agent


@pytest.mark.parametrize("call_name", ["queue_prompt", "upload_image"])
@pytest.mark.spec("comfy.user-agent-preserves-content-type")
def test_the_user_agent_does_not_displace_an_existing_content_type(monkeypatch, call_name):
    # Adding a header must not change what a request already sends: the two POST paths
    # each set their own content type, and both must survive.
    req = _capture_request(monkeypatch, CALLS[call_name])

    assert req.get_header("Content-type"), f"{call_name} lost its Content-Type"
