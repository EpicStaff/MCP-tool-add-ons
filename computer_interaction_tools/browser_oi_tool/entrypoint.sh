#!/usr/bin/env bash
set -e

echo "Clearning old Xvfb displays"
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*

echo "Starting Xvfb virtual display..."
Xvfb $BROWSER_DISPLAY -screen 0 1920x1080x24 &

sleep 2

echo "Starting x11vnc..."
x11vnc -display $BROWSER_DISPLAY -forever -nopw -shared &

echo "Starting noVNC on port 6080..."
websockify --web /usr/share/novnc 6080 0.0.0.0:5900 &

sleep 2

echo "Starting MCP server with Open Interpreter..."
exec poetry run python browser_mcp.py
