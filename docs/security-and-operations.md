# Security and operations boundary

TranscriptForge currently supports one explicit deployment mode: `single_user_local`. It has no
authentication, authorization, account isolation, sharing, or audit identity beyond the fixed
`local-user` owner. The Docker Compose ports bind to loopback, and this mode must not be exposed
directly to the public internet or an untrusted network.

Use a private workstation, private development host, or an access-controlled tunnel/VPN. A public
multi-user application requires an identity provider, project-level authorization, CSRF/session or
token policy, security-event auditing, privacy review, and a new deployment mode. A reverse proxy by
itself does not turn the current application into a supported multi-user service.

## Resource boundaries

- `TRANSCRIPTFORGE_MAX_UPLOAD_BYTES` limits each direct dataset upload; the default is 25 GiB.
- `TRANSCRIPTFORGE_PROJECT_UPLOAD_QUOTA_BYTES` limits persisted dataset-input bytes per project; the
  default is 100 GiB.
- Signature, CIBERSORTx, and external-validation imports have smaller method-specific 5–20 MiB
  limits and row/schema constraints.
- Raw sample sheets and microarray metadata are capped at 5 MiB and 10,000 records.
- Result table pagination is capped at 100 rows per request.
- On API startup, local storage removes only unpublished atomic-write temporary files older than the
  configured 24-hour safety window; published immutable objects are never age-deleted.

The API checks parsed upload size before object publication and charges completed dataset files to
the project quota. Production ingress should enforce an equal or lower request-body limit so an
oversized multipart body is rejected before framework spooling. Generated workflow outputs are not
charged to the input quota; storage capacity and retention therefore still require monitoring.

## Observability

- `GET /api/health` is process liveness and does not depend on PostgreSQL.
- `GET /api/ready` verifies the relational control plane with `SELECT 1`.
- `GET /api/metrics` exposes low-cardinality Prometheus text counters for request count, active
  requests, status classes, and total duration.
- Every API response carries `X-Request-ID`. A safe caller-supplied ID is retained; malformed IDs are
  replaced. One structured completion event records ID, method, path, status, and duration.
- Metrics and request logs never contain request bodies, query strings, uploaded filenames, sample
  identifiers, access tokens, or scientific results.

In a multi-process or horizontally scaled deployment, scrape every process and aggregate externally;
the built-in counters are intentionally process-local. Cloud scientific tasks publish operational
logs to the encrypted CloudWatch group defined by Terraform.

## Public portfolio data policy

Only synthetic fixtures and explicitly documented public GEO studies belong in a public portfolio
deployment. Do not upload PHI, controlled-access genomic data, credentials, private S3 URLs, signed
URLs, institutional identifiers, or unpublished human data. The AWS Batch Terraform is a scientific
execution plane, not a public authenticated web deployment.

Project deletion removes its relational ownership graph. Durable object deletion/retention remains
governed by TD-001 because an owner must choose recovery, legal hold, and partial-failure semantics
before automated destructive cleanup is safe.
