# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Only what's needed to install the local `agents` and `llm` packages
# (per pyproject's [tool.hatch.build.targets.wheel] packages list)
# plus their third-party dependencies. Copied separately from
# src/frontend so UI-only changes don't bust this layer's cache.
COPY pyproject.toml README.md ./
COPY src/agents ./src/agents
COPY src/llm ./src/llm

RUN pip install --no-cache-dir .

# Frontend isn't an installed package -- it's run directly by
# `streamlit run`, so it's copied in last, after the install layer.
COPY src/frontend ./src/frontend

# Render injects $PORT at runtime and requires the container to bind
# to it on 0.0.0.0. 8501 below is only a local-dev fallback.
ENV PORT=8501
EXPOSE 8501

CMD ["sh", "-c", "streamlit run src/frontend/app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true"]
