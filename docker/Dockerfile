FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast, deterministic installs
RUN pip install --no-cache-dir uv

# Copy packaging manifests first so dependency layer is cached
# independently of application code changes.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY dashboard/ ./dashboard/

# Install the package (core deps only; dashboard extras not needed here)
RUN uv pip install --system .

# CMD is not set here — each service in compose.yml supplies its own command.
