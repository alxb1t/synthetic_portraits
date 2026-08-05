# synthetic_portraits

A self-hosted, headless pipeline: **text prompt → photoreal upper-body image of a person
who does not exist** (open SDXL models via ComfyUI on an on-demand RunPod GPU).

> ⚠️ Work in progress. Full usage docs, the demo set, and the **"AI-generated person, not a
> real individual"** disclosure ship in Phase 6.

## Development

Runtime code is **zero third-party dependency** (stdlib only). The dev toolchain is managed
with [uv](https://docs.astral.sh/uv/):

```bash
uv sync            # create the dev environment
uv run pytest      # tests (ComfyUI transport fully mocked — no GPU)
uv run ruff check  # lint
uv run ty check    # type-check
```
