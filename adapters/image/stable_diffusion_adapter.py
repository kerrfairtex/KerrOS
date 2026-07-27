"""
adapters/image/stable_diffusion_adapter.py
===========================================
Image-generation adapter for local Stable Diffusion servers.

Supports two popular backends that share similar REST APIs:

  * **Automatic1111** (AUTOMATIC1111/stable-diffusion-webui)
    Default endpoint: http://localhost:7860
    Set via: SD_A1111_ENDPOINT

  * **ComfyUI** (comfyanonymous/ComfyUI)
    Default endpoint: http://localhost:8188
    Set via: SD_COMFYUI_ENDPOINT

The adapter targets the Automatic1111 /sdapi/v1/txt2img endpoint by
default, which is the most widely deployed.  Set SD_BACKEND=comfyui
to switch to ComfyUI's /prompt API.

Usage::

    from adapters.image.stable_diffusion_adapter import StableDiffusionAdapter
    adapter = StableDiffusionAdapter()
    result = adapter.txt2img("a futuristic cityscape at night")
    # result["images"] contains base64-encoded PNG strings
"""

from __future__ import annotations

import base64
import os
from typing import Any

import requests


class StableDiffusionAdapter:
    """Adapter for local Stable Diffusion image generation."""

    def __init__(
        self,
        *,
        backend: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._backend = (backend or os.getenv("SD_BACKEND", "automatic1111")).lower()
        if self._backend == "comfyui":
            self._base_url = (
                endpoint
                or os.getenv("SD_COMFYUI_ENDPOINT", "http://localhost:8188")
            ).rstrip("/")
        else:
            self._base_url = (
                endpoint
                or os.getenv("SD_A1111_ENDPOINT", "http://localhost:7860")
            ).rstrip("/")
        self.last_error = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def txt2img(
        self,
        prompt: str,
        *,
        negative_prompt: str = "",
        steps: int = 20,
        width: int = 512,
        height: int = 512,
        cfg_scale: float = 7.0,
        sampler: str = "Euler a",
        seed: int = -1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate an image from a text prompt.

        Returns a dict with at minimum:
          ``images`` — list of base64-encoded PNG strings
          ``parameters`` — echo of the generation parameters
          ``backend`` — which backend was used
        """
        if self._backend == "comfyui":
            return self._comfyui_txt2img(prompt, negative_prompt=negative_prompt,
                                          steps=steps, width=width, height=height,
                                          cfg_scale=cfg_scale, seed=seed, **kwargs)
        return self._a1111_txt2img(prompt, negative_prompt=negative_prompt,
                                    steps=steps, width=width, height=height,
                                    cfg_scale=cfg_scale, sampler=sampler,
                                    seed=seed, **kwargs)

    def available(self) -> bool:
        """Return True if the backend server is reachable."""
        try:
            if self._backend == "comfyui":
                r = requests.get(f"{self._base_url}/system_stats", timeout=5)
            else:
                r = requests.get(f"{self._base_url}/sdapi/v1/options", timeout=5)
            return r.status_code < 500
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {
            "provider": "stable_diffusion",
            "backend": self._backend,
            "base_url": self._base_url,
            "available": self.available(),
            "last_error": self.last_error,
        }

    # ── Backend implementations ───────────────────────────────────────────────

    def _a1111_txt2img(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}/sdapi/v1/txt2img"
        body: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": kwargs.get("negative_prompt", ""),
            "steps": kwargs.get("steps", 20),
            "width": kwargs.get("width", 512),
            "height": kwargs.get("height", 512),
            "cfg_scale": kwargs.get("cfg_scale", 7.0),
            "sampler_name": kwargs.get("sampler", "Euler a"),
            "seed": kwargs.get("seed", -1),
        }
        try:
            r = requests.post(url, json=body, timeout=120)
            data = r.json()
            if r.status_code >= 400:
                self.last_error = str(data)
                raise RuntimeError(f"Automatic1111 HTTP {r.status_code}: {data}")
            self.last_error = ""
            return {"images": data.get("images", []),
                    "parameters": data.get("parameters", body),
                    "backend": "automatic1111"}
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def _comfyui_txt2img(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Minimal ComfyUI /prompt call with a basic txt2img workflow."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": prompt, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": kwargs.get("negative_prompt", ""),
                             "clip": ["4", 1]}},
            "4": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}},
            "3": {"class_type": "KSampler",
                  "inputs": {"seed": kwargs.get("seed", 42),
                             "steps": kwargs.get("steps", 20),
                             "cfg": kwargs.get("cfg_scale", 7.0),
                             "sampler_name": "euler",
                             "scheduler": "normal",
                             "denoise": 1.0,
                             "model": ["4", 0],
                             "positive": ["6", 0],
                             "negative": ["7", 0],
                             "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": kwargs.get("width", 512),
                             "height": kwargs.get("height", 512),
                             "batch_size": 1}},
            "8": {"class_type": "VAEDecode",
                  "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage",
                  "inputs": {"filename_prefix": "kerros_",
                             "images": ["8", 0]}},
        }
        try:
            r = requests.post(f"{self._base_url}/prompt",
                              json={"prompt": workflow}, timeout=120)
            data = r.json()
            if r.status_code >= 400:
                self.last_error = str(data)
                raise RuntimeError(f"ComfyUI HTTP {r.status_code}: {data}")
            self.last_error = ""
            # ComfyUI returns a prompt_id; images are fetched separately.
            return {"prompt_id": data.get("prompt_id"),
                    "images": [],
                    "parameters": {"prompt": prompt, **kwargs},
                    "backend": "comfyui",
                    "note": "Poll /history/{prompt_id} to retrieve generated images."}
        except Exception as exc:
            self.last_error = str(exc)
            raise
