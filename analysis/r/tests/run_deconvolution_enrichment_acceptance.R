#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(MCPcounter)
  library(xCell)
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
registry_path <- file.path(root_dir, "apps", "api", "transcriptforge_api", "resources", "deconvolution_methods.json")
assert_true(all(file.exists(c(runner, registry_path))), "Acceptance inputs are missing.")
registry <- fromJSON(registry_path, simplifyVector = FALSE)

root <- tempfile("transcriptforge-enrichment-acceptance-")
dir.create(root)
on.exit(unlink(root, recursive = TRUE), add = TRUE)

build_bundle <- function(method_id, genes, expression_matrix, microarray = FALSE) {
  bundle_parent <- file.path(root, paste0(method_id, "-bundle"))
  bundle_root <- file.path(bundle_parent, "expression_bundle")
  dir.create(file.path(bundle_root, "assays"), recursive = TRUE)
  sample_ids <- colnames(expression_matrix)
  feature_ids <- paste0("feature_", seq_along(genes))
  metadata <- data.frame(sample_id = sample_ids, expected_dominant = sample_ids, stringsAsFactors = FALSE)
  feature_metadata <- data.frame(feature_id = feature_ids, gene_symbol = genes, stringsAsFactors = FALSE)
  write.table(metadata, file.path(bundle_root, "sample_metadata.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
  write.table(feature_metadata, file.path(bundle_root, "feature_metadata.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
  assay_path <- file.path(bundle_root, "assays", "log_expression.tsv.gz")
  assay <- data.frame(feature_id = feature_ids, expression_matrix, check.names = FALSE)
  connection <- gzfile(assay_path, "wt")
  write.table(assay, connection, sep = "\t", quote = FALSE, row.names = FALSE)
  close(connection)
  assay_descriptor <- list(
    name = "log_expression", path = "assays/log_expression.tsv.gz", value_type = "continuous",
    scale = "log2", feature_level = "gene", recommended_for = list("deconvolution"),
    sha256 = sha256_file(assay_path)
  )
  manifest <- list(
    schema_version = "1.0.0", prepared_dataset_id = paste0("prepared-", method_id),
    organism = "Homo sapiens", sample_count = length(sample_ids), feature_count = length(genes),
    sample_metadata = "sample_metadata.tsv", feature_metadata = "feature_metadata.tsv",
    assays = list(assay_descriptor)
  )
  if (microarray) manifest$microarray <- list(platform = "acceptance-array")
  write_json(manifest, file.path(bundle_root, "bundle_manifest.json"))
  bundle_tar <- file.path(root, paste0(method_id, "-expression-bundle.tar.gz"))
  old_working_directory <- getwd()
  setwd(bundle_parent)
  utils::tar(bundle_tar, files = "expression_bundle", compression = "gzip", tar = "internal")
  setwd(old_working_directory)
  list(path = bundle_tar, sha256 = sha256_file(bundle_tar), assay = assay_descriptor, sample_ids = sample_ids)
}

run_method <- function(method_id, reference_filename, bundle, minimum_overlap = 0.95) {
  method <- Filter(function(item) identical(item$id, method_id), registry$methods)[[1L]]
  reference_path <- file.path(root_dir, "references", "deconvolution", reference_filename)
  assert_true(file.exists(reference_path), paste("Missing", method_id, "reference manifest."))
  request_document <- list(
    schema_version = "1.0.0", analysis_id = paste0(method_id, "-acceptance"),
    prepared_dataset_id = paste0("prepared-", method_id), analysis_type = "deconvolution",
    method = method_id, assay = "log_expression", random_seed = 0L,
    parameters = list(reference_profile = method$default_reference, minimum_gene_overlap = minimum_overlap, tumor_mode = FALSE, scale_mrna = TRUE),
    method_registry_version = registry$registry_version,
    method_registry_sha256 = sha256_file(registry_path), deconvolution_method = method,
    input_assay_descriptor = bundle$assay,
    expression_bundle = list(storage_uri = "acceptance://expression-bundle", sha256 = bundle$sha256, size_bytes = file.info(bundle$path)$size)
  )
  run_once <- function(suffix) {
    request_path <- file.path(root, paste0(method_id, "-request-", suffix, ".json"))
    output_dir <- file.path(root, paste0(method_id, "-results-", suffix))
    log_path <- file.path(root, paste0(method_id, "-runner-", suffix, ".log"))
    write_json(request_document, request_path)
    status <- system2(
      "Rscript",
      c(
        shQuote(runner), "--request", shQuote(request_path), "--bundle", shQuote(bundle$path),
        "--reference-manifest", shQuote(reference_path), "--output-dir", shQuote(output_dir)
      ), stdout = log_path, stderr = log_path
    )
    log_text <- paste(readLines(log_path, warn = FALSE), collapse = "\n")
    assert_true(status == 0L, paste(method_id, "runner failed:", log_text))
    expected <- c(
      "deconvolution_results.json", "deconvolution_estimates.tsv", "reference_overlap.tsv",
      "enrichment_scores.svg", "result_manifest.json", "report.qmd", "session_info.txt"
    )
    assert_true(all(file.exists(file.path(output_dir, expected))), paste(method_id, "omitted required artifacts."))
    output_dir
  }
  first <- run_once("first")
  second <- run_once("second")
  first_json <- readBin(file.path(first, "deconvolution_results.json"), "raw", file.info(file.path(first, "deconvolution_results.json"))$size)
  second_json <- readBin(file.path(second, "deconvolution_results.json"), "raw", file.info(file.path(second, "deconvolution_results.json"))$size)
  assert_true(identical(first_json, second_json), paste(method_id, "JSON is not byte-for-byte deterministic."))
  result <- fromJSON(file.path(first, "deconvolution_results.json"), simplifyVector = FALSE)
  assert_true(identical(result$result_type, "enrichment_score"), paste(method_id, "result type is mislabeled."))
  assert_true(identical(result$unit, "arbitrary_score"), paste(method_id, "unit is mislabeled."))
  assert_true(identical(result$composition_constraint, "not_compositional"), paste(method_id, "composition constraint is incorrect."))
  assert_true(is.null(result$composition_summaries), paste(method_id, "must not publish fraction summaries."))
  assert_true(result$input_validation$overlap_fraction >= minimum_overlap, paste(method_id, "overlap audit is incorrect."))
  list(result = result, estimates = read.delim(file.path(first, "deconvolution_estimates.tsv"), check.names = FALSE))
}

marker_path <- "/opt/transcriptforge/deconvolution/MCPcounter_genes.txt"
assert_true(file.exists(marker_path), "Pinned MCP-counter marker asset is unavailable.")
markers <- read.delim(marker_path, check.names = FALSE, stringsAsFactors = FALSE)
mcp_genes <- unique(markers[["HUGO symbols"]])
mcp_dominant <- c("B lineage", "NK cells", "Endothelial cells", "Fibroblasts")
mcp_expression <- matrix(4, nrow = length(mcp_genes), ncol = length(mcp_dominant), dimnames = list(mcp_genes, mcp_dominant))
for (index in seq_along(mcp_dominant)) {
  population_genes <- markers[["HUGO symbols"]][markers[["Cell population"]] == mcp_dominant[[index]]]
  mcp_expression[population_genes, index] <- mcp_expression[population_genes, index] + 8
}
mcp <- run_method("mcp_counter", "mcpcounter_v1.json", build_bundle("mcp_counter", mcp_genes, mcp_expression))
for (sample_id in mcp_dominant) {
  rows <- mcp$estimates[mcp$estimates$sample_id == sample_id, ]
  observed <- rows$cell_type_id[[which.max(rows$value)]]
  assert_true(identical(observed, sample_id), paste("MCP-counter lost the expected dominant population for", sample_id))
}

data_environment <- new.env(parent = emptyenv())
suppressWarnings(utils::data("xCell.data", package = "xCell", envir = data_environment))
xcell_data <- data_environment$xCell.data
xcell_genes <- as.character(xcell_data$genes)
xcell_dominant <- c("B-cells", "NK cells", "Endothelial cells", "Fibroblasts")
xcell_expression <- matrix(
  rep(log2(seq_along(xcell_genes) + 1), length(xcell_dominant)),
  nrow = length(xcell_genes), ncol = length(xcell_dominant),
  dimnames = list(xcell_genes, xcell_dominant)
)
for (index in seq_along(xcell_dominant)) {
  signature_names <- names(xcell_data$signatures)[
    startsWith(names(xcell_data$signatures), paste0(xcell_dominant[[index]], "%"))
  ]
  signature_genes <- unique(unlist(GSEABase::geneIds(xcell_data$signatures[signature_names]), use.names = FALSE))
  signature_genes <- intersect(signature_genes, xcell_genes)
  assert_true(length(signature_genes) > 0L, paste("No xCell signatures found for", xcell_dominant[[index]]))
  xcell_expression[signature_genes, index] <- xcell_expression[signature_genes, index] + 12
}
xcell <- run_method("xcell", "xcell_v1.json", build_bundle("xcell", xcell_genes, xcell_expression))
for (sample_id in xcell_dominant) {
  rows <- xcell$estimates[xcell$estimates$sample_id == sample_id & xcell$estimates$cell_type_id %in% xcell_dominant, ]
  observed <- rows$cell_type_id[[which.max(rows$value)]]
  assert_true(identical(observed, sample_id), paste("xCell lost the expected enriched population for", sample_id))
}

cat("PASS MCP-counter/xCell known-marker recovery, non-compositional semantics, overlap audits, and deterministic JSON\n")
