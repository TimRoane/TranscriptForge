# Contributing

TranscriptForge is under active development. Before opening a change, review the implementation plan and the current checkpoint in `docs/implementation-progress.md`.

## Development workflow

1. Create a focused branch.
2. Add tests for behavior changes.
3. Run `make lint`, `make test`, and `make pipeline-test` as applicable.
4. Keep scientific calculations outside the API and inside tested analysis programs launched by Nextflow.
5. Update the progress ledger when completing a roadmap item.

Never commit human subject data, credentials, local `.env` files, or generated run outputs.
