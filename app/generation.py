"""Replaceable image provider and cancellable background generation."""

import asyncio
import base64
import os
import threading

from openai import AsyncOpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

DEFAULT_PROMPT = (
    "Transform the reference character into an adorable 2D anime chibi desktop companion. "
    "Preserve recognizable hair color, hairstyle, eye color, clothing, accessories, and appearance. "
    "Create a full-body standing character with a large chibi head, small body, expressive eyes, "
    "and clean anime line art. Show the complete character from head to shoes. "
    "Use a transparent background, consistent lighting, and a centered composition. "
    "No text, watermark, scenery, extra characters, or cropped body parts."
)


class OpenAIImageProvider:
    async def generate(self, reference: bytes, prompt: str, key: str) -> bytes:
        async with AsyncOpenAI(api_key=key, base_url="https://api.openai.com/v1",
                               timeout=180, max_retries=0) as client:
            response = await client.images.edit(
                model=os.environ.get("CHIBIMATE_IMAGE_MODEL", "gpt-image-2.5-flare"),
                image=("reference.png", reference, "image/png"), prompt=prompt,
                n=1, size="1024x1024", quality="low", background="transparent", output_format="png",
            )
        if not response.data or not response.data[0].b64_json:
            raise ValueError("No image returned")
        return base64.b64decode(response.data[0].b64_json, validate=True)


class GenerationWorker(QThread):
    result = Signal(bytes)
    error = Signal(str)

    def __init__(self, provider, reference, prompt, key, parent=None):
        super().__init__(parent)
        self.provider, self.reference, self.prompt, self.key = provider, reference, prompt, key
        self.cancelled = threading.Event()

    async def _generate(self):
        task = asyncio.create_task(self.provider.generate(self.reference, self.prompt, self.key))
        try:
            while not task.done():
                if self.cancelled.is_set():
                    task.cancel()
                    break
                await asyncio.wait({task}, timeout=0.05)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def run(self):
        try:
            data = asyncio.run(self._generate())
            if QImage.fromData(data, "PNG").isNull():
                raise ValueError("Invalid generated PNG")
            if not self.cancelled.is_set():
                self.result.emit(data)
        except asyncio.CancelledError:
            pass
        except AuthenticationError:
            self.error.emit("The API key was rejected. Check OPENAI_API_KEY.")
        except RateLimitError:
            self.error.emit("API quota or rate limit reached. Check billing or try again later.")
        except APIConnectionError:
            self.error.emit("Could not connect to OpenAI or the request timed out. Please try again.")
        except APIStatusError:
            self.error.emit("OpenAI could not complete the request. Check model access and your prompt.")
        except Exception:
            # Never expose provider error bodies, keys, prompts, or image data.
            self.error.emit("Generation failed or returned an unreadable PNG. Please try again.")
        finally:
            self.key = ""
            self.reference = b""
