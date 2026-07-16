FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/apps/api

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY apps/api ./apps/api
COPY analysis/python ./analysis/python
COPY analysis/r ./analysis/r
RUN pip install --no-cache-dir .
COPY schemas ./schemas
COPY demo ./demo
COPY pipelines ./pipelines

FROM base AS development
RUN pip install --no-cache-dir '.[dev]'

FROM development AS worker
ARG NXF_VER=25.10.4
ARG QUARTO_VERSION=1.9.38
ENV NXF_VER=${NXF_VER}
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      curl default-jre-headless procps r-base=4.5.0-3 r-bioc-deseq2=1.46.0+dfsg-2 \
      r-bioc-edger=4.4.2+dfsg-1 r-bioc-limma=3.62.2+dfsg-1 \
      r-cran-jsonlite=1.9.1+dfsg-1 \
    && curl --fail --silent --show-error https://get.nextflow.io | bash \
    && install -m 0755 nextflow /usr/local/bin/nextflow \
    && rm nextflow \
    && architecture="$(dpkg --print-architecture)" \
    && if [ "${architecture}" = "arm64" ]; then quarto_arch="aarch64"; else quarto_arch="amd64"; fi \
    && curl --fail --silent --show-error --location \
      "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${quarto_arch}.tar.gz" \
      --output /tmp/quarto.tar.gz \
    && mkdir -p /opt/quarto \
    && tar --extract --gzip --file /tmp/quarto.tar.gz --directory /opt/quarto --strip-components=1 \
    && ln -s /opt/quarto/bin/quarto /usr/local/bin/quarto \
    && quarto --version \
    && rm /tmp/quarto.tar.gz \
    && rm -rf /var/lib/apt/lists/*

FROM base AS production
RUN groupadd --system transcriptforge \
    && useradd --system --gid transcriptforge --home-dir /app transcriptforge \
    && mkdir -p /data/transcriptforge \
    && chown -R transcriptforge:transcriptforge /app /data/transcriptforge
USER transcriptforge
CMD ["uvicorn", "transcriptforge_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
