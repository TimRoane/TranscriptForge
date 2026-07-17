FROM bioconductor/bioconductor_docker:RELEASE_3_23

ARG GSVA_VERSION=2.6.2
ENV GSVA_VERSION=${GSVA_VERSION}

LABEL org.opencontainers.image.title="TranscriptForge signature-scoring runtime" \
      org.opencontainers.image.description="Pinned R 4.6 / Bioconductor 3.23 runtime for GSVA and ssGSEA"

RUN R -q -e 'BiocManager::install(c("GSVA", "jsonlite"), ask = FALSE, update = FALSE)' \
    && R -q -e 'stopifnot(as.character(BiocManager::version()) == "3.23"); stopifnot(as.character(packageVersion("GSVA")) == Sys.getenv("GSVA_VERSION")); packageVersion("BiocParallel"); packageVersion("jsonlite")'

WORKDIR /analysis
