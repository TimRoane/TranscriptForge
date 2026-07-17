#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

assert_true <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

write_json <- function(value, path) {
  writeLines(toJSON(value, auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 16), path)
}

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
assert_true(length(script_argument) == 1L, "Unable to locate the acceptance-test script.")
test_script <- normalizePath(sub("^--file=", "", script_argument[[1L]]))
runner <- normalizePath(file.path(dirname(dirname(test_script)), "signature_scoring.R"))

root <- tempfile("transcriptforge-signature-acceptance-")
dir.create(root)
on.exit(unlink(root, recursive = TRUE), add = TRUE)
bundle_parent <- file.path(root, "bundle")
bundle_root <- file.path(bundle_parent, "expression_bundle")
dir.create(file.path(bundle_root, "assays"), recursive = TRUE)

sample_ids <- c(paste0("control_", 1:4), paste0("treated_", 1:4))
feature_ids <- paste0("gene_", 1:21)
metadata <- data.frame(
  sample_id = sample_ids,
  condition = rep(c("control", "treated"), each = 4L),
  stringsAsFactors = FALSE
)
write.table(metadata, file.path(bundle_root, "sample_metadata.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

set.seed(20260716)
matrix_values <- matrix(rnorm(length(feature_ids) * length(sample_ids), 6, 0.12), nrow = length(feature_ids))
matrix_values[1:5, 5:8] <- matrix_values[1:5, 5:8] + 3
matrix_values[6:10, 5:8] <- matrix_values[6:10, 5:8] - 3
matrix_values[21, ] <- 4
assay <- data.frame(feature_id = feature_ids, matrix_values, check.names = FALSE)
names(assay) <- c("feature_id", sample_ids)
write.table(assay, file.path(bundle_root, "assays", "log_expression.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write_json(
  list(
    schema_version = "1.0.0",
    sample_metadata = "sample_metadata.tsv",
    assays = list(list(name = "log_expression", path = "assays/log_expression.tsv"))
  ),
  file.path(bundle_root, "bundle_manifest.json")
)

bundle_tar <- file.path(root, "expression_bundle.tar.gz")
old_working_directory <- getwd()
setwd(bundle_parent)
utils::tar(bundle_tar, files = "expression_bundle", compression = "gzip", tar = "internal")
setwd(old_working_directory)
bundle_sha256 <- sub("[[:space:]].*$", "", system2("sha256sum", bundle_tar, stdout = TRUE))

signature_set <- function(id, name, feature_numbers) {
  list(
    signature_id = id,
    name = name,
    requested_identifier_count = length(feature_numbers),
    mapped_identifier_count = length(feature_numbers),
    mapping_coverage = 1,
    mapped_entries = lapply(feature_numbers, function(number) list(
      identifier = paste0("G", number), feature_id = paste0("gene_", number)
    ))
  )
}
mapping_report <- list(
  signature_definition_id = "acceptance-definition",
  signature_definition_sha256 = paste(rep("a", 64L), collapse = ""),
  expression_bundle_sha256 = bundle_sha256,
  mapping_coverage = 1,
  requested_identifier_count = 12L,
  mapped_identifier_count = 12L,
  missing_identifier_count = 0L,
  ambiguous_identifier_count = 0L,
  duplicate_identifier_count = 0L,
  sets = list(
    signature_set("positive", "Positive response", c(1:5, 21)),
    signature_set("negative", "Negative response", c(6:10, 21))
  )
)

request_document <- function(method) list(
  schema_version = "1.0.0",
  analysis_id = paste0("acceptance-", method),
  prepared_dataset_id = "prepared-acceptance",
  analysis_type = "signature",
  method = method,
  assay = "log_expression",
  random_seed = 0L,
  parameters = list(
    signature_mapping_id = "acceptance-mapping",
    minimum_gene_set_size = 2L,
    maximum_gene_set_size = 20L,
    gsva_kcdf = "Gaussian",
    gsva_tau = 1,
    gsva_max_diff = TRUE,
    gsva_abs_ranking = FALSE,
    ssgsea_alpha = 0.25,
    ssgsea_normalize = TRUE
  ),
  signature_mapping = list(
    id = "acceptance-mapping",
    report_sha256 = paste(rep("b", 64L), collapse = ""),
    report = mapping_report
  )
)

run_method <- function(method, suffix) {
  request_path <- file.path(root, paste0(method, "-", suffix, "-request.json"))
  output_dir <- file.path(root, paste0(method, "-", suffix, "-results"))
  log_path <- file.path(root, paste0(method, "-", suffix, ".log"))
  write_json(request_document(method), request_path)
  status <- system2(
    "Rscript",
    c(
      shQuote(runner), "--request", shQuote(request_path),
      "--bundle", shQuote(bundle_tar), "--output-dir", shQuote(output_dir)
    ),
    stdout = log_path,
    stderr = log_path
  )
  log_text <- paste(readLines(log_path, warn = FALSE), collapse = "\n")
  assert_true(status == 0L, paste(method, "runner failed:", log_text))
  assert_true(all(file.exists(file.path(output_dir, c(
    "signature_scores.json", "signature_scores.tsv", "scored_features.tsv",
    "signature_scores.svg", "result_manifest.json", "report.qmd", "session_info.txt"
  )))), paste(method, "did not publish every required artifact."))
  output_dir
}

for (method in c("gsva", "ssgsea")) {
  first <- run_method(method, "first")
  second <- run_method(method, "second")
  summary <- fromJSON(file.path(first, "signature_scores.json"), simplifyVector = FALSE)
  sets <- setNames(summary$sets, vapply(summary$sets, function(item) item$signature_id, character(1L)))
  positive <- vapply(sets$positive$scores, function(item) item$score, numeric(1L))
  negative <- vapply(sets$negative$scores, function(item) item$score, numeric(1L))
  assert_true(mean(positive[5:8]) > mean(positive[1:4]), paste(method, "lost the positive response."))
  assert_true(mean(negative[5:8]) < mean(negative[1:4]), paste(method, "lost the negative response."))
  assert_true(
    sets$positive$scored_feature_count == 5L &&
      sets$positive$excluded_constant_feature_count == 1L,
    paste(method, "did not record constant-feature exclusion.")
  )
  assert_true(summary$software$language == "R" && nzchar(summary$software$packages$GSVA), paste(method, "omitted software provenance."))
  assert_true(
    identical(
      readBin(file.path(first, "signature_scores.json"), "raw", file.info(file.path(first, "signature_scores.json"))$size),
      readBin(file.path(second, "signature_scores.json"), "raw", file.info(file.path(second, "signature_scores.json"))$size)
    ),
    paste(method, "JSON result was not byte-for-byte deterministic.")
  )
  cat(sprintf("PASS %s direction, constant filtering, provenance, and deterministic JSON\n", method))
}
