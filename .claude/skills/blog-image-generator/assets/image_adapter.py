"""
Pluggable image adapter for the blog-image-generator skill.

Swap the real provider/key/model in your project .env later — for now these are
DUMMY placeholders so the pipeline is fully wired and never blocks:

    IMAGE_API_PROVIDER=dummy        # dummy | openai | stability | replicate | openrouter
    IMAGE_API_KEY=REPLACE_ME_LATER
    IMAGE_MODEL=REPLACE_ME_LATER

Behavior:
  - provider="dummy" (default): does NOT call any API. Writes a text *brief* next
    to where the image would go and returns its path, so the article still gets
    proper filenames + alt text and the run completes. Swap to a real provider
    when you're ready.
  - provider="openai"/"stability"/"replicate"/"openrouter": real call stubs are
    included; fill the key/model and they work. Kept minimal on purpose.

Public function:
    generate_image(prompt, out_path, size="1200x630", alt_text="") -> str (path written)
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.environ.get("IMAGE_API_PROVIDER", "dummy").lower()
API_KEY = os.environ.get("IMAGE_API_KEY", "REPLACE_ME_LATER")
MODEL = os.environ.get("IMAGE_MODEL", "REPLACE_ME_LATER")


def _write_brief(prompt: str, out_path: Path, size: str, alt_text: str) -> str:
    """No API configured — write an image brief instead of a picture."""
    brief = out_path.with_suffix(".brief.md")
    brief.write_text(
        f"# Image brief (no image API configured)\n\n"
        f"- **Intended file:** {out_path.name}\n"
        f"- **Size:** {size}\n"
        f"- **Alt text:** {alt_text}\n\n"
        f"## Prompt\n{prompt}\n\n"
        f"_Set IMAGE_API_PROVIDER + IMAGE_API_KEY + IMAGE_MODEL in .env to generate for real._\n",
        encoding="utf-8",
    )
    return str(brief)


def _openai(prompt: str, out_path: Path, size: str) -> str:
    # https://platform.openai.com/docs/api-reference/images
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL or "gpt-image-1", "prompt": prompt,
              "size": size.replace("x", "x"), "n": 1},
        timeout=120,
    )
    r.raise_for_status()
    import base64
    b64 = r.json()["data"][0].get("b64_json")
    if b64:
        out_path.write_bytes(base64.b64decode(b64))
    else:                                   # some models return a URL
        url = r.json()["data"][0]["url"]
        out_path.write_bytes(requests.get(url, timeout=120).content)
    return str(out_path)


def _stability(prompt: str, out_path: Path, size: str) -> str:
    # Stability AI — fill endpoint/model per your account
    r = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={"Authorization": f"Bearer {API_KEY}", "Accept": "image/*"},
        files={"none": ""},
        data={"prompt": prompt, "output_format": "png"},
        timeout=120,
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return str(out_path)


def _generic_url_provider(prompt: str, out_path: Path, size: str) -> str:
    """Placeholder for replicate/openrouter/other — you'll paste the exact call."""
    raise NotImplementedError(
        f"Provider '{PROVIDER}' not wired yet. Tell Claude which API and it fills this in."
    )


def generate_image(prompt: str, out_path, size: str = "1200x630", alt_text: str = "") -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if PROVIDER == "dummy" or API_KEY in ("", "REPLACE_ME_LATER"):
        return _write_brief(prompt, out_path, size, alt_text)

    try:
        if PROVIDER == "openai":
            return _openai(prompt, out_path, size)
        if PROVIDER == "stability":
            return _stability(prompt, out_path, size)
        return _generic_url_provider(prompt, out_path, size)
    except Exception as e:
        print(f"  ! image generation failed ({PROVIDER}): {e} — writing brief instead")
        return _write_brief(prompt, out_path, size, alt_text)


if __name__ == "__main__":
    # quick self-test in dummy mode
    p = generate_image("A clean minimal illustration of an online JSON formatter tool",
                       "images/json-formatter-featured.png",
                       alt_text="Illustration of a JSON formatter web tool")
    print("wrote:", p)
