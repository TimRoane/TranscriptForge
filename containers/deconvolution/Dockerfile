FROM bioconductor/bioconductor_docker:RELEASE_3_22

ARG QUANTISEQR_VERSION=1.18.0
ARG QUANTISEQR_SHA256=ac0cf7804b70d759237eb4c8fbc9e1b37b81384653fd6f97f109f57ade1ddd68
ENV QUANTISEQR_VERSION=${QUANTISEQR_VERSION}
ARG MCPCOUNTER_COMMIT=b6eac73e91c246fcff0bb1a5c68a816cd588fc48
ARG MCPCOUNTER_SHA256=fa97668e63b25765eea5bf136fac8ce9117e063a44a7e8f5d94387d7af10270d
ARG MCPCOUNTER_MARKERS_SHA256=408f6c5d02c8f9bd2f1599c598367881853520934f8ce398a4886a8b296922bb
ARG XCELL_COMMIT=20e2919eefd37e15af35f29f4944e30697098a28
ARG XCELL_SHA256=042780994eb8363cd673e598a5355e3bffc33cb51052722ca885657e63eaeb0e

LABEL org.opencontainers.image.title="TranscriptForge deconvolution runtime" \
      org.opencontainers.image.description="Pinned R / Bioconductor 3.22 runtime for audited quanTIseq, MCP-counter, and xCell analysis"

RUN R -q -e 'BiocManager::install(c("Biobase", "preprocessCore", "SummarizedExperiment", "limSolve", "ggplot2", "tidyr", "rlang", "jsonlite"), ask = FALSE, update = FALSE)' \
    && curl --fail --silent --show-error --location \
      "https://bioconductor.org/packages/3.22/bioc/src/contrib/quantiseqr_${QUANTISEQR_VERSION}.tar.gz" \
      --output /tmp/quantiseqr.tar.gz \
    && echo "${QUANTISEQR_SHA256}  /tmp/quantiseqr.tar.gz" | sha256sum --check \
    && R CMD INSTALL /tmp/quantiseqr.tar.gz \
    && R -q -e 'stopifnot(as.character(BiocManager::version()) == "3.22"); stopifnot(as.character(packageVersion("quantiseqr")) == Sys.getenv("QUANTISEQR_VERSION")); packageVersion("jsonlite")' \
    && rm /tmp/quantiseqr.tar.gz

RUN R -q -e 'BiocManager::install(c("GSVA", "GSEABase", "curl", "digest", "pracma", "quadprog"), ask = FALSE, update = FALSE)' \
    && curl --fail --silent --show-error --location \
      "https://github.com/ebecht/MCPcounter/archive/${MCPCOUNTER_COMMIT}.tar.gz" \
      --output /tmp/mcpcounter.tar.gz \
    && echo "${MCPCOUNTER_SHA256}  /tmp/mcpcounter.tar.gz" | sha256sum --check \
    && mkdir -p /tmp/mcpcounter /opt/transcriptforge/deconvolution \
    && tar --extract --gzip --file /tmp/mcpcounter.tar.gz --directory /tmp/mcpcounter --strip-components=1 \
    && echo "${MCPCOUNTER_MARKERS_SHA256}  /tmp/mcpcounter/Signatures/genes.txt" | sha256sum --check \
    && install -m 0444 /tmp/mcpcounter/Signatures/genes.txt /opt/transcriptforge/deconvolution/MCPcounter_genes.txt \
    && R CMD INSTALL /tmp/mcpcounter/Source \
    && curl --fail --silent --show-error --location \
      "https://github.com/dviraran/xCell/archive/${XCELL_COMMIT}.tar.gz" \
      --output /tmp/xcell.tar.gz \
    && echo "${XCELL_SHA256}  /tmp/xcell.tar.gz" | sha256sum --check \
    && mkdir -p /tmp/xcell \
    && tar --extract --gzip --file /tmp/xcell.tar.gz --directory /tmp/xcell --strip-components=1 \
    && R CMD INSTALL /tmp/xcell \
    && R -q -e 'stopifnot(as.character(packageVersion("MCPcounter")) == "1.2.0"); stopifnot(as.character(packageVersion("xCell")) == "1.1.0")' \
    && rm -rf /tmp/mcpcounter /tmp/mcpcounter.tar.gz /tmp/xcell /tmp/xcell.tar.gz

WORKDIR /analysis
