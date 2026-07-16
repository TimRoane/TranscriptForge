# TranscriptForge

TranscriptForge is a research-use platform for reproducible human transcriptomics analysis. It combines a React interface, a FastAPI service, durable Celery workers, and containerized Nextflow DSL2 workflows.

> [!IMPORTANT]
> TranscriptForge is intended for research and software demonstration only. It is not clinically validated and must not be used for diagnosis or patient-care decisions.

## Current status

Development is following the vertical-slice roadmap in [`TranscriptForge_Codex_Implementation_Plan.md`](TranscriptForge_Codex_Implementation_Plan.md). The precise implementation checkpoint and next task are recorded in [`docs/implementation-progress.md`](docs/implementation-progress.md).

## Local development

Prerequisites:

- Docker with Compose v2
- GNU Make
- Optional for host-side checks: Python 3.12+, Node.js 22.13+, and Nextflow 25+

Start the development stack:

```bash
cp .env.example .env
make dev
```

The web interface is served at <http://localhost:5173>, the API at <http://localhost:8000>, and API documentation at <http://localhost:8000/docs>.

Dataset validation and preparation runs update directly on the project dashboard. Active cards poll durable run state and move through `QUEUED`, `STARTING`, `RUNNING`, and a terminal state. Completed validation cards render findings and orientation previews; prepared-dataset pages render QC, mapping coverage, assay inventory, and immutable artifact downloads. From an Expression Bundle, launch PCA, hierarchical clustering, UMAP, or t-SNE and follow the live run to interactive coordinates, variance, dendrogram, correlation, static SVG downloads, a self-contained Quarto report, and Nextflow provenance views. The Phase 4 design builder previews differential-expression formulas, contrasts, assay-aware method routing, replication, and model-matrix rank before a design can be saved. Raw-count designs default to DESeq2 and can alternatively run through edgeR quasi-likelihood or limma-voom; continuous log-expression designs route to limma. All four engines expose interactive volcano/MA plots, p-value distributions, top-feature expression heatmaps, searchable and sortable result tables, filtered downloads, per-gene statistics and expression profiles, the R-side design matrix, diagnostics, reports, and provenance on the same live analysis page. Researchers can select up to 500 result genes and save a named candidate-signature draft that freezes the source run, result checksum, result rows, and active selection criteria; the interface explicitly distinguishes these candidates from an independently validated signature.

Useful commands:

```bash
make stop           # stop local services
make test           # run API and frontend tests
make test-r         # run DESeq2/limma scientific acceptance fixtures in the pinned worker
make test-all       # run application tests plus the R acceptance harness
make lint           # run static checks
make pipeline-test  # run the Nextflow smoke workflow
make generate-large-demo  # regenerate the deterministic 72-sample study
make seed-demo      # load, prepare, and analyze that study through the API
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md), [`docs/data-contracts.md`](docs/data-contracts.md), and [`docs/local-development.md`](docs/local-development.md).

## License

Licensed under the [MIT License](LICENSE).
