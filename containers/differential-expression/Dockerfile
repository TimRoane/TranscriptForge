FROM bioconductor/bioconductor_docker:RELEASE_3_23

LABEL org.opencontainers.image.title="TranscriptForge differential-expression runtime" \
      org.opencontainers.image.description="Pinned R 4.6 / Bioconductor 3.23 runtime for differential expression"

RUN R -q -e 'BiocManager::install(c("DESeq2", "limma", "edgeR", "jsonlite"), ask = FALSE, update = FALSE)' \
    && R -q -e 'stopifnot(as.character(BiocManager::version()) == "3.23"); packageVersion("DESeq2"); packageVersion("edgeR"); packageVersion("limma")'

WORKDIR /analysis
