FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" docker redis pydantic-settings websockets httpx

COPY api/ ./api/

EXPOSE 8100

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8100"]
