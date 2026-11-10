FROM node:22-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/agent-venv/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    HOST=0.0.0.0 \
    PORT=8787 \
    WESTBAHN_PYTHON=/opt/agent-venv/bin/python \
    WESTBAHN_BROWSER_PROFILE=/app/server/data/westbahn-browser \
    WESTBAHN_LEDGER=/app/server/data/westbahn.json

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && python3 -m venv /opt/agent-venv \
    && rm -rf /var/lib/apt/lists/*
COPY server/browser/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/playwright-browsers \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=node:node server /app/server
COPY --chown=node:node src/core /app/src/core
COPY --chown=node:node package.json /app/package.json
RUN mkdir -p /app/server/data && chown -R node:node /app/server/data
WORKDIR /app/server
USER node
EXPOSE 8787
VOLUME ["/app/server/data"]
CMD ["node","index.mjs"]
