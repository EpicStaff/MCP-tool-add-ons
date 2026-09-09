# Base Python image
FROM python:3.12.10-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y \
    curl git wget unzip vim \
    x11vnc xvfb x11-utils x11-apps \
    libx11-6 libgtk-3-0 libgl1-mesa-glx \
    novnc websockify scrot \
    chromium chromium-driver \
    libnss3 libxss1 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libxcomposite1 libxcursor1 libxdamage1 libxrandr2 libgbm1 \
    libpango1.0-0 fontconfig fonts-liberation \
    socat \
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
RUN poetry run playwright install chromium
COPY . /app/

# --- Data volume ---
VOLUME /app/data

# --- Environment variables ---
ARG MCP_BROWSER_OPEN_INTERPRETER_PORT
ENV MCP_BROWSER_OPEN_INTERPRETER_PORT=${MCP_BROWSER_OPEN_INTERPRETER_PORT}

ENV DISPLAY=:99
EXPOSE ${MCP_BROWSER_OPEN_INTERPRETER_PORT}
EXPOSE 5900
EXPOSE 6080

# --- Start Xvfb and VNC + MCP entrypoint ---
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
