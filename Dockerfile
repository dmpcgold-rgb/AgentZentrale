FROM node:22-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/agent-venv/bin:$PATH \
    HOST=0.0.0.0 \
    PORT=8787 \
    WESTBAHN_PYTHON=/opt/agent-venv/bin/python \
    WESTBAHN_CHROMIUM_PATH=/usr/bin/chromium \
    WESTBAHN_BROWSER_PROFILE=/app/server/data/westbahn-browser \
    WESTBAHN_LEDGER=/app/server/data/westbahn.json

WORKDIR /app
# Debian provides Chromium for both amd64 and arm64. Avoid the browser-download
# and dependency-install subprocesses of Playwright on the Oracle ARM VM.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates chromium fonts-liberation libatomic1 xvfb x11vnc novnc websockify xauth \
    && rm -rf /var/lib/apt/lists/*
RUN /usr/bin/python3 -m venv /opt/agent-venv
COPY server/browser/requirements.txt /tmp/requirements.txt
RUN /opt/agent-venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt
RUN /usr/bin/chromium --version \
    && /opt/agent-venv/bin/python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop()'
COPY --chown=node:node server /app/server
# Fail the Docker build if any Python browser module contains a syntax error.
# The previous image must never be replaced with code that cannot import.
RUN /opt/agent-venv/bin/python -m compileall -q /app/server/browser
COPY --chown=node:node src/core /app/src/core
COPY --chown=node:node package.json /app/package.json
# Do not deploy checkout changes until the standalone ledger and receipt tests pass.
RUN node --test server/tests/westbahn.test.mjs
RUN mkdir -p /app/server/data && chown -R node:node /app/server/data
WORKDIR /app/server
USER node
EXPOSE 8787
VOLUME ["/app/server/data"]
CMD ["node","index.mjs"]
