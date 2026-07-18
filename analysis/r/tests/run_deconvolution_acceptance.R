#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(quantiseqr)
})

assert_true <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

write_json <- function(value, path) {
  writeLines(toJSON(value, auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 16), path)
}

sha256_file <- function(path) {
  sub("[[:space:]].*$", "", system2("sha256sum", path, stdout = TRUE)[[1L]])
}

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
assert_true(length(script_argument) == 1L, "Unable to locate the acceptance-test script.")
test_script <- normalizePath(sub("^--file=", "", script_argument[[1L]]))
root_dir <- normalizePath(file.path(dirname(test_script), "..", "..", ".."))
runner <- file.path(root_dir, "analysis", "r", "deconvolution.R")
reference_path <- file.path(root_dir, "references", "deconvolution", "quantiseq_til10.json")
registry_path <- file.path(root_dir, "apps", "api", "transcriptforge_api", "resources", "deconvolution_methods.json")
assert_true(all(file.exists(c(runner, reference_path, registry_path))), "Acceptance inputs are missing.")

root <- tempfile("transcriptforge-deconvolution-acceptance-")
dir.create(root)
on.exit(unlink(root, recursive = TRUE), add = TRUE)
bundle_parent <- file.path(root, "bundle")
bundle_root <- file.path(bundle_parent, "expression_bundle")
dir.create(file.path(bundle_root, "assays"), recursive = TRUE)

signature_path <- system.file("extdata", "TIL10_signature.txt", package = "quantiseqr", mustWork = TRUE)
signature <- as.matrix(read.delim(signature_path, check.names = FALSE, row.names = 1))
fractions <- matrix(0.025, nrow = ncol(signature), ncol = 4L)
rownames(fractions) <- colnames(signature)
colnames(fractions) <- c("b_cell_rich", "nk_rich", "cd8_rich", "neutrophil_rich")
dominant <- c("B.cells", "NK.cells", "T.cells.CD8", "Neutrophils")
for (index in seq_along(dominant)) fractions[dominant[[index]], index] <- 0.775
mixtures <- signature %*% fractions
mixtures <- t(t(mixtures) * 1e6 / colSums(mixtures))

# Split one symbol across duplicate feature rows and add one explicitly unmapped row.
feature_ids <- paste0("feature_", seq_len(nrow(mixtures)))
feature_symbols <- rownames(mixtures)
first_half <- mixtures[1L, , drop = FALSE] / 2
mixtures[1L, ] <- first_half
mixtures <- rbind(mixtures, first_half, unmapped = rep(0, ncol(mixtures)))
feature_ids <- c(feature_ids, "feature_duplicate", "feature_unmapped")
feature_symbols <- c(feature_symbols, feature_symbols[[1L]], "")
rownames(mixtures) <- feature_ids

sample_ids <- colnames(mixtures)
metadata <- data.frame(sample_id = sample_ids, expected_dominant = dominant, stringsAsFactors = FALSE)
feature_metadata <- data.frame(
  feature_id = feature_ids, gene_symbol = feature_symbols, stringsAsFactors = FALSE
)
write.table(metadata, file.path(bundle_root, "sample_metadata.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write.table(feature_metadata, file.path(bundle_root, "feature_metadata.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

assay_path <- file.path(bundle_root, "assays", "tpm.tsv.gz")
assay <- data.frame(feature_id = feature_ids, mixtures, check.names = FALSE)
connection <- gzfile(assay_path, "wt")
write.table(assay, connection, sep = "\t", quote = FALSE, row.names = FALSE)
close(connection)
assay_sha256 <- sha256_file(assay_path)
assay_descriptor <- list(
  name = "tpm", path = "assays/tpm.tsv.gz", value_type = "nonnegative_continuous",
  scale = "linear", feature_level = "gene", recommended_for = list("deconvolution"),
  sha256 = assay_sha256
)
write_json(
  list(
    schema_version = "1.0.0", prepared_dataset_id = "prepared-acceptance",
    organism = "Homo sapiens", sample_count = length(sample_ids), feature_count = nrow(mixtures),
    sample_metadata = "sample_metadata.tsv", feature_metadata = "feature_metadata.tsv",
    assays = list(assay_descriptor)
  ),
  file.path(bundle_root, "bundle_manifest.json")
)

bundle_tar <- file.path(root, "expression_bundle.tar.gz")
old_working_directory <- getwd()
setwd(bundle_parent)
utils::tar(bundle_tar, files = "expression_bundle", compression = "gzip", tar = "internal")
setwd(old_working_directory)
bundle_sha256 <- sha256_file(bundle_tar)
registry <- fromJSON(registry_path, simplifyVector = FALSE)
method <- Filter(function(item) identical(item$id, "quantiseq"), registry$methods)[[1L]]

request_document <- list(
  schema_version = "1.0.0", analysis_id = "deconvolution-acceptance",
  prepared_dataset_id = "prepared-acceptance", analysis_type = "deconvolution",
  method = "quantiseq", assay = "tpm", random_seed = 0L,
  parameters = list(reference_profile = "TIL10", minimum_gene_overlap = 0.95, tumor_mode = FALSE, scale_mrna = FALSE),
  method_registry_version = registry$registry_version,
  method_registry_sha256 = sha256_file(registry_path),
  deconvolution_method = method,
  input_assay_descriptor = assay_descriptor,
  expression_bundle = list(storage_uri = "acceptance://expression-bundle", sha256 = bundle_sha256, size_bytes = file.info(bundle_tar)$size)
)

run_once <- function(suffix) {
  request_path <- file.path(root, paste0("request-", suffix, ".json"))
  output_dir <- file.path(root, paste0("results-", suffix))
  log_path <- file.path(root, paste0("runner-", suffix, ".log"))
  write_json(request_document, request_path)
  status <- system2(
    "Rscript",
    c(
      shQuote(runner), "--request", shQuote(request_path), "--bundle", shQuote(bundle_tar),
      "--reference-manifest", shQuote(reference_path), "--output-dir", shQuote(output_dir)
    ),
    stdout = log_path, stderr = log_path
  )
  log_text <- paste(readLines(log_path, warn = FALSE), collapse = "\n")
  assert_true(status == 0L, paste("quanTIseq runner failed:", log_text))
  expected <- c(
    "deconvolution_results.json", "deconvolution_estimates.tsv", "reference_overlap.tsv",
    "cell_fractions.svg", "result_manifest.json", "report.qmd", "session_info.txt"
  )
  assert_true(all(file.exists(file.path(output_dir, expected))), "Runner omitted required artifacts.")
  output_dir
}

first <- run_once("first")
second <- run_once("second")
result <- fromJSON(file.path(first, "deconvolution_results.json"), simplifyVector = FALSE)
estimate <- read.delim(file.path(first, "deconvolution_estimates.tsv"), check.names = FALSE)
for (index in seq_along(sample_ids)) {
  rows <- estimate[estimate$sample_id == sample_ids[[index]] & estimate$cell_type_id != "Other", ]
  observed <- rows$cell_type_id[[which.max(rows$value)]]
  assert_true(identical(observed, dominant[[index]]), paste("Lost expected dominant population for", sample_ids[[index]]))
}
assert_true(result$input_validation$overlap_fraction >= 0.99, "Reference overlap audit is incorrect.")
assert_true(result$input_validation$blank_symbol_count == 1L, "Blank-symbol exclusion was not audited.")
assert_true(result$input_validation$duplicate_symbol_count == 1L, "Duplicate-symbol collapse was not audited.")
assert_true(all(vapply(result$composition_summaries, function(item) item$within_tolerance, logical(1L))), "Fractions do not sum to one.")
first_json <- readBin(file.path(first, "deconvolution_results.json"), "raw", file.info(file.path(first, "deconvolution_results.json"))$size)
second_json <- readBin(file.path(second, "deconvolution_results.json"), "raw", file.info(file.path(second, "deconvolution_results.json"))$size)
assert_true(identical(first_json, second_json), "Deconvolution JSON is not byte-for-byte deterministic.")
cat("PASS quanTIseq dominant-population recovery, overlap audit, composition, and deterministic JSON\n")
