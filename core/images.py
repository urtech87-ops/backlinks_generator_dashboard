"""
Images for the dashboard's content agent.

This does NOT reimplement image generation. The pluggable adapter already lives
at `.claude/skills/blog-image-generator/assets/image_adapter.py` — that file is
the one place the user (or Claude Code) edits when they pick a real provider, so
the dashboard loads *that* module and calls its `generate_image()`.

Two small adjustments are needed to use it from a long-running app:

  1. it reads the provider/key/model into module globals at import time, so
     after Settings writes a new key we refresh those globals from `core.config`
     before every call — otherwise the dashboard would keep using whatever was
     set when the app started.
  2. it must never take the dashboard down, so a missing adapter file (or any
     exception inside it) falls back to writing the same kind of image *brief*
     the adapter writes in dummy mode.

`generate()` therefore always returns a written file: a picture when an image
API is configured, an image brief when it isn't. Drafting never blocks on this
(CLAUDE.md).
"""

import importlib.util
from pathlib import Path

from . import config

ADAPTER_PATH = (config.ROOT / ".claude" / "skills" / "blog-image-generator"
                / "assets" / "image_adapter.py")

DUMMY = "dummy"
_adapter = None          # cached module, loaded once per process


def provider() -> str:
    """The image provider currently selected in Settings ('dummy' by default)."""
    return config.get("IMAGE_API_PROVIDER", DUMMY).strip().lower() or DUMMY


def live() -> bool:
    """True when a real image API is configured — otherwise we write briefs."""
    return provider() != DUMMY and config.is_set("IMAGE_API_KEY")


def status() -> str:
    """One plain-language line for the UI."""
    if live():
        model = config.get("IMAGE_MODEL")
        return f"Images will be generated with {provider()}{f' ({model})' if model else ''}."
    return ("No image API configured, so the agent writes a detailed image brief per "
            "image instead. Drafting carries on either way.")


def _load_adapter():
    """Import the skill's adapter module by path. None if it isn't there."""
    global _adapter
    if _adapter is not None:
        return _adapter
    if not ADAPTER_PATH.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("blog_image_adapter", ADAPTER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _adapter = module
        return _adapter
    except Exception:
        return None


def _sync(module) -> None:
    """Point the adapter at whatever Settings holds right now."""
    module.PROVIDER = provider()
    module.API_KEY = config.get("IMAGE_API_KEY", "REPLACE_ME_LATER")
    module.MODEL = config.get("IMAGE_MODEL", "REPLACE_ME_LATER")


def _fallback_brief(prompt: str, out_path: Path, size: str, alt_text: str) -> str:
    """Same brief the adapter writes, for when the adapter file can't be loaded."""
    brief = out_path.with_suffix(".brief.md")
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(
        f"# Image brief (no image API configured)\n\n"
        f"- **Intended file:** {out_path.name}\n"
        f"- **Size:** {size}\n"
        f"- **Alt text:** {alt_text}\n\n"
        f"## Prompt\n{prompt}\n\n"
        f"_Set IMAGE_API_PROVIDER + IMAGE_API_KEY + IMAGE_MODEL in Settings to "
        f"generate for real._\n",
        encoding="utf-8",
    )
    return str(brief)


def generate(prompt: str, out_path, size: str = "1200x630", alt_text: str = "") -> dict:
    """
    Make one image (or its brief). Returns
    {'path': str, 'brief': bool, 'detail': str} and never raises.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    module = _load_adapter()
    if module is None:
        path = _fallback_brief(prompt, out_path, size, alt_text)
        return {"path": path, "brief": True,
                "detail": "Image adapter not found — wrote a brief instead."}

    try:
        _sync(module)
        path = module.generate_image(prompt, out_path, size=size, alt_text=alt_text)
    except Exception as e:
        path = _fallback_brief(prompt, out_path, size, alt_text)
        return {"path": path, "brief": True,
                "detail": f"Image generation failed ({provider()}): {e} — wrote a brief."}

    is_brief = str(path).endswith(".brief.md")
    return {"path": str(path), "brief": is_brief,
            "detail": ("Image brief written — no image API configured." if is_brief
                       else f"Image generated with {provider()}.")}
