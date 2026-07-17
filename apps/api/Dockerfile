FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/apps/api:/app/analysis/python

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY apps/api ./apps/api
COPY analysis/python ./analysis/python
COPY analysis/r ./analysis/r
RUN pip install --no-cache-dir .
COPY schemas ./schemas
COPY microarray ./microarray
COPY demo ./demo
COPY pipelines ./pipelines

FROM base AS development
RUN pip install --no-cache-dir '.[dev]'

FROM development AS worker
ARG NXF_VER=25.10.4
ARG QUARTO_VERSION=1.9.38
ARG SALMON_VERSION=1.11.4
ARG AWS_CLI_VERSION=2.27.49
ARG BIOMANAGER_VERSION=1.30.27
ARG BIOMANAGER_SHA256=acbfdcf09602c8279085556ca54531c2ada0ac3c1775d54ce2c3b9a3dc03fbb5
ARG GSVA_VERSION=2.4.9
ENV GSVA_VERSION=${GSVA_VERSION}
ARG SALMON_SHA256_AMD64=59dba764d579630a4ebbfaf7bb9575f1a72bbe215e76af3187d82b4665794833
ARG SALMON_SHA256_ARM64=930cf75009a2f0a705a6acc6f4613d2add03f00961893333cd750570b6431198
ENV NXF_VER=${NXF_VER}
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      build-essential curl default-jre-headless fastp=0.24.0+dfsg-1 \
      fastqc=0.12.1+dfsg-4 gfortran libblas-dev libcurl4-openssl-dev libhdf5-dev \
      libicu-dev liblapack-dev libmagick++-dev libpng-dev libsqlite3-dev libssl-dev \
      libxml2-dev locales procps unzip \
      r-base=4.5.0-3 r-bioc-deseq2=1.46.0+dfsg-2 \
      r-bioc-edger=4.4.2+dfsg-1 r-bioc-limma=3.62.2+dfsg-1 \
      r-bioc-tximport=1.34.0+dfsg-2 r-cran-jsonlite=1.9.1+dfsg-1 \
    && localedef --inputfile=en_US --charmap=UTF-8 en_US.UTF-8
RUN curl --fail --silent --show-error --location \
      "https://cloud.r-project.org/src/contrib/BiocManager_${BIOMANAGER_VERSION}.tar.gz" \
      --output /tmp/BiocManager.tar.gz \
    && echo "${BIOMANAGER_SHA256}  /tmp/BiocManager.tar.gz" | sha256sum --check \
    && R CMD INSTALL /tmp/BiocManager.tar.gz \
    && R -q -e 'BiocManager::install(version = "3.22", ask = FALSE, update = FALSE)' \
    && rm /tmp/BiocManager.tar.gz
RUN R -q -e 'BiocManager::install("BiocSingular", ask = FALSE, update = FALSE); stopifnot(requireNamespace("BiocSingular", quietly = TRUE))'
RUN R -q -e 'BiocManager::install("GSVA", ask = FALSE, update = FALSE); stopifnot(as.character(BiocManager::version()) == "3.22"); stopifnot(as.character(packageVersion("GSVA")) == Sys.getenv("GSVA_VERSION")); packageVersion("BiocParallel")'
RUN pip install --no-cache-dir multiqc==1.32 \
    && architecture="$(dpkg --print-architecture)" \
    && if [ "${architecture}" = "arm64" ]; then aws_arch="aarch64"; else aws_arch="x86_64"; fi \
    && curl --fail --silent --show-error --location \
      "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}-${AWS_CLI_VERSION}.zip" \
      --output /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && aws --version \
    && curl --fail --silent --show-error https://get.nextflow.io | bash \
    && install -m 0755 nextflow /usr/local/bin/nextflow \
    && rm nextflow \
    && architecture="$(dpkg --print-architecture)" \
    && if [ "${architecture}" = "arm64" ]; then salmon_arch="aarch64"; salmon_sha="${SALMON_SHA256_ARM64}"; else salmon_arch="x86_64"; salmon_sha="${SALMON_SHA256_AMD64}"; fi \
    && curl --fail --silent --show-error --location \
      "https://github.com/COMBINE-lab/salmon/releases/download/v${SALMON_VERSION}/salmon-linux-${salmon_arch}.tar.gz" \
      --output /tmp/salmon.tar.gz \
    && echo "${salmon_sha}  /tmp/salmon.tar.gz" | sha256sum --check \
    && tar --extract --gzip --file /tmp/salmon.tar.gz --directory /usr/local/bin \
      --strip-components=2 "salmon-linux-${salmon_arch}/bin/salmon" \
    && salmon --version \
    && if [ "${architecture}" = "arm64" ]; then quarto_arch="aarch64"; else quarto_arch="amd64"; fi \
    && curl --fail --silent --show-error --location \
      "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${quarto_arch}.tar.gz" \
      --output /tmp/quarto.tar.gz \
    && mkdir -p /opt/quarto \
    && tar --extract --gzip --file /tmp/quarto.tar.gz --directory /opt/quarto --strip-components=1 \
    && ln -s /opt/quarto/bin/quarto /usr/local/bin/quarto \
    && quarto --version \
    && rm -rf /tmp/aws /tmp/awscliv2.zip /tmp/quarto.tar.gz /tmp/salmon.tar.gz \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

FROM base AS production
RUN groupadd --system transcriptforge \
    && useradd --system --gid transcriptforge --home-dir /app transcriptforge \
    && mkdir -p /data/transcriptforge \
    && chown -R transcriptforge:transcriptforge /app /data/transcriptforge
USER transcriptforge
CMD ["uvicorn", "transcriptforge_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
