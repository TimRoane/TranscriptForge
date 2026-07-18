# Releasing TranscriptForge

Releases are owner-triggered and non-commercially licensed. Keep the Python package, root npm
package, web package, and API `__version__` identical, then validate them locally:

```bash
.venv/bin/python scripts/validate_release.py
```

After the complete CI and scientific acceptance matrix passes, create and push an annotated stable
semantic-version tag matching that version:

```bash
git tag -a v0.1.0 -m "TranscriptForge v0.1.0"
git push origin v0.1.0
```

The tag-only release workflow builds the production API, nginx-hosted web application, and pinned
scientific worker. It publishes version and commit tags to GHCR, records the registry-provided digest
for each image, generates SBOM/provenance attestations, and attaches `release-images.json` to the
GitHub release. Deploy by the `name@sha256:...` identities in that manifest, never by a mutable tag.

The workflow does not provision AWS or accept third-party terms. An AWS deployment must still pass
the account-specific threat-model, budget, networking, and checksum-parity gates described under
[`infra/aws`](../infra/aws/README.md).
