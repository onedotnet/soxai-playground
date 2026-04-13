"""Playground configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Limits
    max_sessions: int = 5
    session_timeout_minutes: int = 30
    idle_timeout_minutes: int = 10

    # Docker
    sandbox_image: str = "soxai-playground-sandbox:latest"
    sandbox_cpu_limit: float = 1.0      # cores
    sandbox_mem_limit: str = "1g"       # memory
    sandbox_network: str = "playground" # docker network

    # Redis (for queue)
    redis_url: str = "redis://localhost:6379/1"

    # Preview
    preview_domain: str = "play.soxai.io"

    # Public hostname for this API (used in WebSocket URLs returned to clients)
    public_url: str = "https://playground-dev.soxai.io"

    # SoxAI Gateway (AI requests go through gateway, not API server)
    soxai_base_url: str = "https://gateway-dev.soxai.io"

    model_config = {
        "env_prefix": "PLAYGROUND_",
        "env_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
    }


settings = Settings()
