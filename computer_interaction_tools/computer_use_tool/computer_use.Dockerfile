# Base Python image
FROM python:3.12.10-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y \
    curl git wget unzip procps \
    docker.io docker-compose \
    && rm -rf /var/lib/apt/lists/*

# --- Poetry ---
RUN pip install poetry
ENV PATH="/root/.local/bin:$PATH" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# --- App setup ---
WORKDIR /app
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-root --only main -vvv
COPY . /app/

# Note: At runtime, this container needs access to the Docker socket:
# -v /var/run/docker.sock:/var/run/docker.sock
# This allows the MCP server to manage the desktop container via docker-compose

# --- Data volume ---
VOLUME /app/output

# --- Environment variables ---
ARG MCP_COMPUTER_USE_PORT
ENV MCP_COMPUTER_USE_PORT=${MCP_COMPUTER_USE_PORT}

# Set environment variables for os_computer_use
ENV OCU_DESKTOP_CONTAINER=ocu-desktop
ENV OCU_DESKTOP_DISPLAY=:0
ENV OCU_DESKTOP_HOST=localhost
ENV OCU_DESKTOP_NOVNC_PORT=6080

# --- Expose port for MCP API ---
EXPOSE ${MCP_COMPUTER_USE_PORT}

CMD ["poetry", "run", "python", "computer_use_mcp.py"]

