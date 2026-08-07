"""The transport seam to ComfyUI.

Every ComfyUI call goes through the :class:`ComfyTransport` Protocol so the rest of the
package never touches HTTP directly. :class:`ComfyClient` is the real implementation
(stdlib ``urllib`` only — the runtime stays zero-dependency); :class:`FakeComfyClient`
replays the ``/prompt`` -> poll ``/history`` -> ``/view`` state machine in-memory so no
test ever hits a GPU or the network.

The poll loop itself lives in :func:`await_outputs`, a pure function over the transport,
so the state machine and its error paths are unit-testable against the fake.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

__all__ = [
    "ComfyClient",
    "ComfyError",
    "ComfyExecutionError",
    "ComfyTimeoutError",
    "ComfyTransport",
    "FakeComfyClient",
    "await_outputs",
]


# --- Errors -----------------------------------------------------------------


class ComfyError(Exception):
    """Base for all transport-level failures."""


class ComfyExecutionError(ComfyError):
    """The server rejected the prompt or a node failed during execution."""


class ComfyTimeoutError(ComfyError):
    """Polling ``/history`` exceeded ``max_polls`` without a result."""


# --- The seam ---------------------------------------------------------------


@runtime_checkable
class ComfyTransport(Protocol):
    """The four operations the pipeline needs from ComfyUI."""

    def upload_image(self, filename: str, data: bytes) -> str:
        """Upload image bytes; return the server-side name to reference in a graph."""
        ...

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Queue an API-format workflow graph; return its ``prompt_id``."""
        ...

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        """Fetch the history entry for ``prompt_id`` (empty until it completes)."""
        ...

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Fetch rendered image bytes from ``/view``."""
        ...


def await_outputs(
    transport: ComfyTransport,
    prompt_id: str,
    *,
    max_polls: int = 300,
    interval: float = 1.0,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    """Poll ``/history`` until ``prompt_id`` completes; return its ``outputs`` bucket.

    Raises :class:`ComfyExecutionError` if the server reports a node error, and
    :class:`ComfyTimeoutError` if it never completes within ``max_polls``.
    """
    for _ in range(max_polls):
        history = transport.get_history(prompt_id)
        entry = history.get(prompt_id)
        if entry is not None:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise ComfyExecutionError(_describe_error(status, prompt_id))
            return entry.get("outputs", {})
        sleep(interval)
    raise ComfyTimeoutError(f"prompt {prompt_id} did not complete within {max_polls} polls")


def _describe_error(status: dict[str, Any], prompt_id: str) -> str:
    for _event, payload in status.get("messages", []):
        detail = payload.get("exception_message") or payload.get("exception_type")
        if detail:
            return f"prompt {prompt_id} failed: {detail}"
    return f"prompt {prompt_id} failed during execution"


# --- Real implementation (stdlib urllib) ------------------------------------


class ComfyClient:
    """HTTP transport to a ComfyUI server over stdlib ``urllib``."""

    def __init__(self, base_url: str, *, client_id: str | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex
        self.timeout = timeout

    def upload_image(self, filename: str, data: bytes) -> str:
        content_type, body = _encode_multipart(filename, data)
        req = Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return self._json(req).get("name", filename)

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode()
        req = Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        result = self._json(req)
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ComfyExecutionError(f"no prompt_id in response: {result!r}")
        return prompt_id

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        req = Request(f"{self.base_url}/history/{prompt_id}", method="GET")
        return self._json(req)

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        query = urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
        req = Request(f"{self.base_url}/view?{query}", method="GET")
        return self._bytes(req)

    # -- low-level request helpers --

    def _bytes(self, req: Request) -> bytes:
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            raise ComfyExecutionError(_read_http_error(exc)) from exc
        except URLError as exc:
            raise ComfyError(f"cannot reach ComfyUI at {self.base_url}: {exc.reason}") from exc

    def _json(self, req: Request) -> dict[str, Any]:
        raw = self._bytes(req)
        return json.loads(raw) if raw else {}


def _encode_multipart(filename: str, data: bytes) -> tuple[str, bytes]:
    """Encode a single image field as ``multipart/form-data`` (returns content-type, body)."""
    boundary = f"----synthportraits{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="image"; '
            + f'filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    return f"multipart/form-data; boundary={boundary}", body


def _read_http_error(exc: HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:  # noqa: BLE001 - best-effort error detail
        raw = b""
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode(errors="replace")
        return parsed.get("error") or json.dumps(parsed)
    return f"HTTP {exc.code}: {exc.reason}"


# --- In-memory fake (replays the state machine) -----------------------------

_DEFAULT_OUTPUTS: dict[str, Any] = {
    "9": {
        "images": [{"filename": "synthetic_portrait_00001_.png", "subfolder": "", "type": "output"}]
    }
}

# A 1x1 PNG so ``get_image`` returns plausible image bytes by default.
_ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6360000002000100"
    "05000106a9a06c0000000049454e44ae426082"
)


class FakeComfyClient:
    """Scriptable in-memory transport that replays the poll state machine.

    ``polls_until_done`` controls how many ``get_history`` calls return *pending*
    (``{}``) before the outputs appear — the poll loop under test. Set ``queue_error``
    to reject at queue time, or ``execution_error`` to fail during execution.
    """

    def __init__(
        self,
        *,
        polls_until_done: int = 1,
        outputs: dict[str, Any] | None = None,
        view_bytes: bytes = _ONE_PX_PNG,
        queue_error: str | None = None,
        execution_error: str | None = None,
    ):
        self.polls_until_done = polls_until_done
        self.outputs = _DEFAULT_OUTPUTS if outputs is None else outputs
        self.view_bytes = view_bytes
        self.queue_error = queue_error
        self.execution_error = execution_error

        self.uploads: list[tuple[str, bytes]] = []
        self.queued_workflows: list[dict[str, Any]] = []
        self.requested_views: list[tuple[str, str, str]] = []
        self.poll_count = 0

    def upload_image(self, filename: str, data: bytes) -> str:
        self.uploads.append((filename, data))
        return filename

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        if self.queue_error is not None:
            raise ComfyExecutionError(self.queue_error)
        self.queued_workflows.append(workflow)
        return f"fake-prompt-{len(self.queued_workflows):04d}"

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        self.poll_count += 1
        if self.poll_count < self.polls_until_done:
            return {}  # still pending
        if self.execution_error is not None:
            status = {
                "status_str": "error",
                "completed": False,
                "messages": [["execution_error", {"exception_message": self.execution_error}]],
            }
            return {prompt_id: {"outputs": {}, "status": status}}
        return {
            prompt_id: {
                "outputs": self.outputs,
                "status": {"status_str": "success", "completed": True},
            }
        }

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        self.requested_views.append((filename, subfolder, folder_type))
        return self.view_bytes
