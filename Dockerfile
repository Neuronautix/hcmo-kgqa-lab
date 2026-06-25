# syntax=docker/dockerfile:1
FROM python:3.11-slim

# --- System build dependencies --------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Install the package (dependencies resolved from pyproject) ------------
# Editable install: `app` is imported from /app/app (the source tree / mounted
# volume) rather than a frozen copy baked into site-packages. A non-editable
# `pip install .` shadowed the ./app bind mount and resolved asset paths under
# site-packages, so the UI silently ran stale build-time code.
COPY pyproject.toml README.md ./
COPY app/ ./app/
# A BuildKit cache mount keeps downloaded wheels across (re)builds so flaky
# networks can resume instead of re-fetching everything; retries/timeout add
# resilience to transient pythonhosted.org read timeouts.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 -e .

# --- Copy runtime assets ---------------------------------------------------
COPY ontology/ ./ontology/
COPY kg/ ./kg/
COPY shacl/ ./shacl/
COPY sparql/ ./sparql/

EXPOSE 8501

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
