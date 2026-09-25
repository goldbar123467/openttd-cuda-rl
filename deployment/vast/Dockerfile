FROM nvidia/cuda:12.8.1-devel-ubuntu24.04@sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build git ca-certificates curl unzip \
    python3 python3-venv python3-dev python3-jsonschema python3-packaging pkg-config \
    libssl-dev liblzma-dev liblzo2-dev libzstd-dev libpng-dev zlib1g-dev \
    libfreetype-dev libfontconfig1-dev libicu-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/openttd-venv \
    && /opt/openttd-venv/bin/python -m pip install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128 \
    && /opt/openttd-venv/bin/python -m pip install --no-cache-dir jsonschema==4.26.0 numpy==2.2.6

ENV PATH=/opt/openttd-venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES=0 \
    CUBLAS_WORKSPACE_CONFIG=:4096:8 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    RL_DATA_ROOT=/data/openttd-study

# Use this directory as the Docker build context. Source is fetched by exact
# revision on the persistent volume; no credentials or local runs enter image.
COPY entrypoint.py /opt/openttd-entrypoint.py
ENTRYPOINT ["/opt/openttd-venv/bin/python", "/opt/openttd-entrypoint.py"]
