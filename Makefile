.PHONY: dev stop logs migrate test test-api test-web test-r test-signature-r test-signature-cross-modality test-raw-rnaseq test-microarray test-all lint pipeline-test generate-large-demo seed-demo terraform-check aws-batch-preflight aws-batch-acceptance

dev:
	docker compose up --build -d

stop:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose run --rm api alembic -c apps/api/alembic.ini upgrade head

test: test-api test-web

test-api:
	python3 -m pytest apps/api/tests analysis/python/tests

test-web:
	npm --workspace @transcriptforge/web test -- --run

test-r:
	docker compose run --rm --no-deps worker \
		Rscript /app/analysis/r/tests/run_differential_expression_acceptance.R

test-signature-r:
	docker compose run --rm --no-deps worker \
		Rscript /app/analysis/r/tests/run_signature_scoring_acceptance.R

test-signature-cross-modality:
	python3 -m pytest analysis/python/tests/test_cross_modality_signature.py

test-raw-rnaseq:
	demo/raw_rnaseq/run_acceptance.sh

test-microarray:
	docker build -t transcriptforge/microarray:bioc-3.23 containers/microarray
	docker compose build api worker
	demo/microarray/run_acceptance.sh

test-all: test test-r test-signature-r

lint:
	python3 -m ruff check apps/api analysis/python demo/large_experiment
	python3 -m mypy apps/api/transcriptforge_api analysis/python/transcriptforge_analysis
	npm --workspace @transcriptforge/web run lint

pipeline-test:
	nextflow run pipelines/main.nf -entry RUN_DEMO -profile test --outdir .nextflow-test-results
	nextflow run pipelines/main.nf -entry VALIDATE_DATASET -profile test -resume --validation_config demo/configs/count_matrix_validation.json --matrix demo/data/counts.tsv --metadata demo/metadata/sample_metadata.tsv --outdir .nextflow-test-results
	nextflow run pipelines/main.nf -entry PREPARE_DATASET -profile test -resume --validation_config demo/configs/count_matrix_validation.json --matrix demo/data/counts.tsv --metadata demo/metadata/sample_metadata.tsv --outdir .nextflow-test-results

seed-demo:
	python3 demo/large_experiment/seed.py

generate-large-demo:
	python3 demo/large_experiment/generate.py

terraform-check:
	docker run --rm --user "$(shell id -u):$(shell id -g)" -v "$(CURDIR)/infra/aws/terraform:/workspace" -w /workspace hashicorp/terraform:1.13 fmt -check
	docker run --rm --user "$(shell id -u):$(shell id -g)" -v "$(CURDIR)/infra/aws/terraform:/workspace" -w /workspace hashicorp/terraform:1.13 init -backend=false -input=false
	docker run --rm --user "$(shell id -u):$(shell id -g)" -v "$(CURDIR)/infra/aws/terraform:/workspace" -w /workspace hashicorp/terraform:1.13 validate

aws-batch-preflight:
	python3 scripts/aws/validate_batch_profile.py --live

aws-batch-acceptance:
	scripts/aws/run_batch_acceptance.sh
