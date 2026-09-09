#!/bin/bash
set -e

# No password required

# Start Xvfb (virtual display)
# Full HD resolution (1920x1080)
echo "Starting Xvfb..."
Xvfb :0 -screen 0 1920x1080x24 &
XVFB_PID=$!
sleep 2

# Allow all X11 connections (needed for screenshots from root)
export DISPLAY=:0
xhost + || true

# Start window manager
echo "Starting Fluxbox..."
DISPLAY=:0 fluxbox &
FLUXBOX_PID=$!
sleep 1

# Start x11vnc without password
echo "Starting x11vnc..."
x11vnc -display :0 -forever -shared -nopw -rfbport 5900 &
X11VNC_PID=$!
sleep 2

# Start noVNC websockify on port 8080
echo "Starting noVNC..."
websockify --web=/usr/share/novnc 8080 localhost:5900 &
WEBSOCKIFY_PID=$!

# Set up port forwarding to host machine for backend access
# This allows localhost:8000 in container to forward to host.docker.internal:8000
echo "Setting up port forwarding to host machine..."
socat TCP-LISTEN:8000,fork,reuseaddr TCP:host.docker.internal:8000 &
SOCAT_8000_PID=$!

# Optional: Also forward port 4200 if needed
socat TCP-LISTEN:4200,fork,reuseaddr TCP:host.docker.internal:4200 &
SOCAT_4200_PID=$!

echo "======================================"
echo "Desktop environment started!"
echo "noVNC: http://localhost:6080/vnc.html"
echo "VNC: localhost:5900"
echo "Port forwarding:"
echo "  - localhost:8000 -> host backend:8000"
echo "  - localhost:4200 -> host frontend:4200"
echo "No password required"
echo "======================================"

# Keep container running and handle signals
trap "kill $XVFB_PID $FLUXBOX_PID $X11VNC_PID $WEBSOCKIFY_PID $SOCAT_8000_PID $SOCAT_4200_PID 2>/dev/null" EXIT SIGTERM SIGINT

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
