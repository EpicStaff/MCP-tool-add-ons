FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:0 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Base desktop + automation tooling
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        fluxbox \
        xterm \
        novnc \
        websockify \
        x11-xserver-utils \
        xdotool \
        scrot \
        imagemagick \
        ffmpeg \
        python3 \
        python3-pip \
        curl \
        wget \
        unzip \
        bzip2 \
        xz-utils \
        procps \
        ca-certificates \
        fonts-dejavu \
        fonts-liberation \
        libgtk-3-0 \
        libdbus-glib-1-2 \
        libxt6 \
        libxcomposite1 \
        libgl1 \
        socat && \
    rm -rf /var/lib/apt/lists/*

# Install Firefox ESR directly from Mozilla to avoid snap dependencies
RUN wget -O /tmp/firefox.tar.bz2 "https://download.mozilla.org/?product=firefox-esr-latest&os=linux64&lang=en-US" && \
    tar -xf /tmp/firefox.tar.bz2 -C /opt && \
    ln -s /opt/firefox/firefox /usr/local/bin/firefox-esr && \
    rm /tmp/firefox.tar.bz2

COPY startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

EXPOSE 5900 6080

CMD ["/usr/local/bin/startup.sh"]
