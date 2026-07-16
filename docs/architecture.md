# Architecture

TranscriptForge separates product orchestration from scientific computation.

```text
React web client
      |
      v
FastAPI REST API ---- PostgreSQL
      |              object storage
      v
Redis / Celery worker
      |
      v
Nextflow DSL2 ---- containerized R and Python programs
      |
      v
Expression Bundles / Result Bundles / provenance
```

The API validates request shape, persists records, freezes parameter JSON, and queues work. It must never implement scientific statistics. A worker launches Nextflow with an argument array, records execution identity and state transitions, and indexes published artifacts after successful manifest validation.

Local development uses filesystem-backed run storage plus MinIO for exercising the S3-compatible adapter. Production-like execution uses PostgreSQL and Redis. Scientific processes will receive purpose-built immutable containers and deterministic seeds.

Differential-expression requests cross two validation boundaries. FastAPI builds a preview model
matrix from immutable bundle metadata before a design can be saved. The R process independently
rebuilds that design and refuses to fit unless its formula, sample count, column count, and rank
match the frozen preview. Raw counts route by default to DESeq2, with edgeR quasi-likelihood and
limma-voom as explicit alternatives; continuous log-expression assays route to limma. All four
engines publish a common results table/plot boundary while retaining method-specific abundance,
normalization, filtering, and test-statistic semantics. The API performs read-only pagination, filtering, and sorting
over the immutable published table; it does not recompute statistics. Per-feature views join that
table to the engine-published normalized-expression profiles and sample metadata.

Candidate gene signatures are orchestration records, not new statistical results. A draft belongs
to one project and references the exact prepared dataset, differential-expression analysis, and
successful source run. It stores selected feature identifiers, snapshots their published result
rows, and records the immutable result artifact identifier and SHA-256 checksum. This preserves the
selection decision even if later runs produce different estimates. Candidate drafts are kept
separate from trained `ModelRecord` objects and never imply independent or clinical validation.

## Service boundaries

- `apps/api`: HTTP API, persistence, storage abstraction, queueing, and run orchestration.
- `apps/web`: typed UI, forms, run monitoring, and manifest-driven result rendering.
- `pipelines`: workflow routing, channel wiring, and process definitions.
- `analysis`: tested scientific libraries and thin command-line wrappers.
- `schemas`: cross-language contracts for every durable bundle and request.
- `containers`: scientific runtime image definitions.

## Trust boundaries

Uploaded names are display metadata only. Server paths and object keys are generated internally. User data is never interpolated into a shell string. Nextflow is launched with a fixed executable and an argument list. Artifact serving must resolve paths inside the owning run namespace.
