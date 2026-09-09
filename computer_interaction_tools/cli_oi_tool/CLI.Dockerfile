# Base Python image
FROM python:3.12.10-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y \
    curl git wget unzip procps \
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

# --- Data volume (optional if needed) ---
VOLUME /app/data

# --- Environment variables ---
ENV CLI_TOOL_MODE=true

ARG MCP_CLI_OPEN_INTERPRETER_PORT
ENV MCP_CLI_OPEN_INTERPRETER_PORT=${MCP_CLI_OPEN_INTERPRETER_PORT}

# --- Expose port for MCP API ---
EXPOSE ${MCP_CLI_OPEN_INTERPRETER_PORT}

CMD ["poetry", "run", "python", "cli_mcp.py"]

