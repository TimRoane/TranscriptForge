# Local development

Copy `.env.example` to `.env`, then run `make dev`. Docker Compose starts:

- Web UI: <http://localhost:5173>
- API: <http://localhost:8000>
- OpenAPI UI: <http://localhost:8000/docs>
- MinIO API: <http://localhost:9000>
- MinIO console: <http://localhost:9001>

Check service state with `docker compose ps` and follow logs with `make logs`. Stop services with `make stop`; named volumes intentionally retain database, queue, object, and run data.

Host-side development uses `pip install -e '.[dev]'` and `npm install`. Run `make test`, `make lint`, and `make pipeline-test` before handing off a change.

Never use real patient data in the development profile.
