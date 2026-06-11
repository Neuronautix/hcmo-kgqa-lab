FROM python:3.11-slim

# --- System build dependencies --------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Install the package (dependencies resolved from pyproject) ------------
COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN pip install --no-cache-dir .

# --- Copy runtime assets ---------------------------------------------------
COPY ontology/ ./ontology/
COPY kg/ ./kg/
COPY shacl/ ./shacl/
COPY sparql/ ./sparql/

EXPOSE 8501

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
