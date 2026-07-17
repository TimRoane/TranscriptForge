FROM bioconductor/bioconductor_docker:RELEASE_3_23

LABEL org.opencontainers.image.title="TranscriptForge Affymetrix microarray runtime" \
      org.opencontainers.image.description="Pinned Bioconductor 3.23 runtime for oligo RMA"

RUN R -q -e 'BiocManager::install(c("oligo", "pd.hugene.1.0.st.v1", "hugene10sttranscriptcluster.db", "jsonlite"), ask = FALSE, update = FALSE)' \
    && R -q -e 'stopifnot(as.character(BiocManager::version()) == "3.23"); packageVersion("oligo"); packageVersion("pd.hugene.1.0.st.v1"); packageVersion("hugene10sttranscriptcluster.db")'

WORKDIR /analysis
