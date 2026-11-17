from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit

from .errors import SynthesisError


@dataclass(frozen=True)
class Config:
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: str = field(default="", repr=False)
    image: str = "python:3.11-slim"
    max_model_calls: int = 40
    max_tool_calls: int = 120
    command_timeout_sec: int = 30
    api_timeout_sec: int = 90
    max_file_bytes: int = 256_000
    max_total_bytes: int = 2_000_000
    max_files: int = 100
    max_output_bytes: int = 64_000
    max_response_bytes: int = 1_000_000
    max_context_bytes: int = 4_000_000
    max_completion_tokens: int = 8000
    memory_mb: int = 256
    cpus: float = 1.0
    pids_limit: int = 64

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if name not in {"base_url", "model", "api_key", "image", "cpus"}:
                value = getattr(self, name)
                if type(value) is not int or value <= 0:
                    raise SynthesisError(f"{name} must be a positive integer")
        if not isinstance(self.cpus, (float, int)) or not 0 < self.cpus <= 64:
            raise SynthesisError("cpus must be in (0, 64]")
        url = urlsplit(self.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise SynthesisError("base_url must be an HTTP(S) endpoint without credentials/query")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise SynthesisError("remote model endpoints require HTTPS")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]*", self.image):
            raise SynthesisError("invalid configured image")
        if not isinstance(self.model, str) or not isinstance(self.api_key, str):
            raise SynthesisError("model and api_key must be strings")

    @classmethod
    def from_env(cls, **overrides):
        values = {
            "base_url": os.getenv("SYNTHESIS_BASE_URL", os.getenv("OPENAI_BASE_URL", cls.base_url)),
            "model": os.getenv("SYNTHESIS_MODEL", ""),
            "api_key": os.getenv("SYNTHESIS_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            "image": os.getenv("SYNTHESIS_IMAGE", cls.image),
        }
        values.update(overrides)
        return cls(**values)

    def public(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "api_key"}
