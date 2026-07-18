FROM bioconductor/bioconductor_docker:RELEASE_3_22

ARG QUANTISEQR_VERSION=1.18.0
ARG QUANTISEQR_SHA256=ac0cf7804b70d759237eb4c8fbc9e1b37b81384653fd6f97f109f57ade1ddd68
ENV QUANTISEQR_VERSION=${QUANTISEQR_VERSION}

LABEL org.opencontainers.image.title="TranscriptForge quanTIseq runtime" \
      org.opencontainers.image.description="Pinned R / Bioconductor 3.22 runtime for audited quanTIseq TIL10 deconvolution"

RUN R -q -e 'BiocManager::install(c("Biobase", "preprocessCore", "SummarizedExperiment", "limSolve", "ggplot2", "tidyr", "rlang", "jsonlite"), ask = FALSE, update = FALSE)' \
    && curl --fail --silent --show-error --location \
      "https://bioconductor.org/packages/3.22/bioc/src/contrib/quantiseqr_${QUANTISEQR_VERSION}.tar.gz" \
      --output /tmp/quantiseqr.tar.gz \
    && echo "${QUANTISEQR_SHA256}  /tmp/quantiseqr.tar.gz" | sha256sum --check \
    && R CMD INSTALL /tmp/quantiseqr.tar.gz \
    && R -q -e 'stopifnot(as.character(BiocManager::version()) == "3.22"); stopifnot(as.character(packageVersion("quantiseqr")) == Sys.getenv("QUANTISEQR_VERSION")); packageVersion("jsonlite")' \
    && rm /tmp/quantiseqr.tar.gz

WORKDIR /analysis
