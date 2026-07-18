#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(quantiseqr)
})

abort <- function(message) stop(message, call. = FALSE)

parse_args <- function(values) {
  result <- list()
  index <- 1L
  while (index <= length(values)) {
    key <- values[[index]]
    if (!startsWith(key, "--") || index == length(values)) abort(paste("Invalid argument:", key))
    result[[substring(key, 3L)]] <- values[[index + 1L]]
    index <- index + 2L
  }
  result
}

write_json <- function(value, path) {
  writeLines(toJSON(value, auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 16), path)
}

sha256_file <- function(path) {
  output <- system2("sha256sum", path, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if ((!is.null(status) && status != 0L) || length(output) != 1L) {
    abort(paste("Unable to calculate SHA-256 for", basename(path)))
  }
  sub("[[:space:]].*$", "", output[[1L]])
}

safe_path <- function(root, relative) {
  if (startsWith(relative, "/") || any(strsplit(relative, "/", fixed = TRUE)[[1L]] == "..")) {
    abort(paste("Expression Bundle contains an unsafe path:", relative))
  }
  file.path(root, relative)
}

same_value <- function(left, right) identical(left, right) || identical(as.character(left), as.character(right))

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("request", "bundle", "reference-manifest", "output-dir")
missing_args <- required[!required %in% names(args)]
if (length(missing_args)) abort(paste("Missing arguments:", paste(missing_args, collapse = ", ")))

request <- fromJSON(args$request, simplifyVector = FALSE)
reference <- fromJSON(args$`reference-manifest`, simplifyVector = FALSE)
if (!identical(request$analysis_type, "deconvolution")) abort("Request is not deconvolution.")
if (!identical(request$method, "quantiseq")) abort("Only the audited quanTIseq runner is available.")
if (!identical(request$assay, "tpm")) abort("quanTIseq requires linear, non-log TPM input.")
if (!identical(request$parameters$reference_profile, "TIL10")) abort("quanTIseq requires TIL10.")
if (!identical(reference$method, "quantiseq") || !identical(reference$id, "TIL10")) {
  abort("The reference manifest is not the pinned quanTIseq TIL10 reference.")
}
if (!identical(as.character(packageVersion("quantiseqr")), reference$package$version)) {
  abort("Installed quantiseqr version differs from the pinned reference manifest.")
}

reference_sha256 <- sha256_file(args$`reference-manifest`)
request_sha256 <- sha256_file(args$request)
bundle_sha256 <- sha256_file(args$bundle)
if (is.null(request$expression_bundle$sha256) || !identical(bundle_sha256, request$expression_bundle$sha256)) {
  abort("Expression Bundle checksum differs from the frozen analysis request.")
}

for (item in reference$files) {
  relative <- sub("^extdata/", "", item$package_path)
  installed_path <- system.file("extdata", relative, package = "quantiseqr", mustWork = TRUE)
  if (!identical(sha256_file(installed_path), item$sha256)) {
    abort(paste("Installed quanTIseq reference checksum differs for", item$package_path))
  }
}

output_dir <- args$`output-dir`
if (dir.exists(output_dir)) abort(paste("Output directory already exists:", output_dir))
dir.create(output_dir, recursive = TRUE)
extract_dir <- tempfile("transcriptforge-deconvolution-")
dir.create(extract_dir)
on.exit(unlink(extract_dir, recursive = TRUE), add = TRUE)
members <- untar(args$bundle, list = TRUE)
if (any(startsWith(members, "/")) || any(grepl("(^|/)\\.\\.(/|$)", members))) {
  abort("Expression Bundle archive contains an unsafe member path.")
}
untar(args$bundle, exdir = extract_dir)
bundle_root <- file.path(extract_dir, "expression_bundle")
manifest_path <- file.path(bundle_root, "bundle_manifest.json")
if (!file.exists(manifest_path)) abort("Expression Bundle manifest is missing.")
bundle_manifest <- fromJSON(manifest_path, simplifyVector = FALSE)
if (!identical(bundle_manifest$organism, reference$organism)) {
  abort("Expression Bundle organism differs from the pinned reference.")
}

assay_index <- which(vapply(
  bundle_manifest$assays,
  function(item) identical(item$name, request$assay),
  logical(1L)
))
if (length(assay_index) != 1L) abort("TPM assay is missing or duplicated in the bundle.")
assay_descriptor <- bundle_manifest$assays[[assay_index]]
for (field in c("name", "scale", "value_type", "feature_level", "sha256")) {
  if (!same_value(assay_descriptor[[field]], request$input_assay_descriptor[[field]])) {
    abort(paste("Bundle assay descriptor differs from frozen request field:", field))
  }
}
if (!identical(assay_descriptor$scale, "linear") ||
    !identical(assay_descriptor$value_type, "nonnegative_continuous") ||
    !identical(assay_descriptor$feature_level, "gene")) {
  abort("quanTIseq requires nonnegative continuous, linear, gene-level TPM input.")
}

assay_path <- safe_path(bundle_root, assay_descriptor$path)
metadata_path <- safe_path(bundle_root, bundle_manifest$sample_metadata)
feature_metadata_path <- safe_path(bundle_root, bundle_manifest$feature_metadata)
if (!all(file.exists(c(assay_path, metadata_path, feature_metadata_path)))) {
  abort("Bundle assay, sample metadata, or feature metadata is missing.")
}
if (!identical(sha256_file(assay_path), assay_descriptor$sha256)) {
  abort("TPM assay checksum differs from the bundle manifest.")
}

metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
feature_metadata <- read.delim(feature_metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
assay_frame <- read.delim(assay_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!"sample_id" %in% names(metadata) || anyDuplicated(metadata$sample_id)) {
  abort("Sample metadata must contain unique sample_id values.")
}
if (ncol(assay_frame) < 2L || names(assay_frame)[[1L]] != "feature_id" || anyDuplicated(assay_frame$feature_id)) {
  abort("TPM assay must begin with unique feature_id values and contain sample columns.")
}
if (!all(c("feature_id", "gene_symbol") %in% names(feature_metadata)) || anyDuplicated(feature_metadata$feature_id)) {
  abort("Feature metadata must contain unique feature_id and gene_symbol columns.")
}
sample_ids <- names(assay_frame)[-1L]
if (!setequal(sample_ids, metadata$sample_id)) abort("Assay and metadata sample identifiers do not match.")
expression_matrix <- as.matrix(assay_frame[, -1L, drop = FALSE])
storage.mode(expression_matrix) <- "numeric"
rownames(expression_matrix) <- assay_frame$feature_id
colnames(expression_matrix) <- sample_ids
if (any(!is.finite(expression_matrix)) || any(expression_matrix < 0)) {
  abort("TPM assay contains negative or non-finite values.")
}

feature_metadata <- feature_metadata[match(rownames(expression_matrix), feature_metadata$feature_id), , drop = FALSE]
if (any(is.na(feature_metadata$feature_id))) abort("TPM features are missing from feature metadata.")
symbols <- trimws(as.character(feature_metadata$gene_symbol))
mapped <- !is.na(symbols) & nzchar(symbols)
blank_symbol_count <- sum(!mapped)
mapped_symbols <- symbols[mapped]
duplicate_symbol_count <- sum(duplicated(mapped_symbols))
symbol_matrix <- rowsum(expression_matrix[mapped, , drop = FALSE], mapped_symbols, reorder = FALSE)
if (!nrow(symbol_matrix)) abort("No TPM features have usable gene symbols.")

signature_path <- system.file("extdata", "TIL10_signature.txt", package = "quantiseqr", mustWork = TRUE)
signature <- read.delim(signature_path, check.names = FALSE, row.names = 1)
effective_genes <- rownames(signature)
rm_genes_path <- system.file("extdata", "TIL10_rmgenes.txt", package = "quantiseqr", mustWork = TRUE)
rm_genes <- readLines(rm_genes_path, warn = FALSE)
effective_genes <- setdiff(effective_genes, rm_genes)
if (isTRUE(request$parameters$tumor_mode)) {
  tumor_path <- system.file("extdata", "TIL10_TCGA_aberrant_immune_genes.txt", package = "quantiseqr", mustWork = TRUE)
  effective_genes <- setdiff(effective_genes, readLines(tumor_path, warn = FALSE))
}
overlap_genes <- intersect(effective_genes, rownames(symbol_matrix))
overlap_fraction <- length(overlap_genes) / length(effective_genes)
minimum_overlap <- as.numeric(request$parameters$minimum_gene_overlap)
if (!is.finite(minimum_overlap) || minimum_overlap < 0 || minimum_overlap > 1) {
  abort("minimum_gene_overlap must be between zero and one.")
}
if (overlap_fraction < minimum_overlap) {
  abort(sprintf(
    "quanTIseq reference overlap %.1f%% is below the frozen minimum %.1f%% (%d/%d genes).",
    100 * overlap_fraction, 100 * minimum_overlap, length(overlap_genes), length(effective_genes)
  ))
}

results <- quantiseqr::run_quantiseq(
  expression_data = symbol_matrix,
  signature_matrix = "TIL10",
  is_arraydata = FALSE,
  is_tumordata = isTRUE(request$parameters$tumor_mode),
  scale_mRNA = isTRUE(request$parameters$scale_mrna),
  method = "lsei",
  rm_genes = "default",
  return_se = FALSE
)
if (!identical(as.character(results$Sample), sample_ids)) abort("quanTIseq returned an unexpected sample order.")
cell_type_ids <- names(results)[-1L]
expected_cell_types <- vapply(reference$cell_types, function(item) item$id, character(1L))
if (!identical(cell_type_ids, expected_cell_types)) abort("quanTIseq returned unexpected cell types.")
estimate_matrix <- as.matrix(results[, -1L, drop = FALSE])
storage.mode(estimate_matrix) <- "numeric"
if (any(!is.finite(estimate_matrix)) || any(estimate_matrix < -1e-12)) {
  abort("quanTIseq returned invalid cell fractions.")
}
estimate_matrix[estimate_matrix < 0] <- 0

estimate_rows <- list()
cursor <- 1L
for (sample_index in seq_along(sample_ids)) {
  for (cell_index in seq_along(cell_type_ids)) {
    estimate_rows[[cursor]] <- list(
      sample_id = sample_ids[[sample_index]],
      cell_type_id = cell_type_ids[[cell_index]],
      value = as.numeric(estimate_matrix[sample_index, cell_index])
    )
    cursor <- cursor + 1L
  }
}
reported_sums <- rowSums(estimate_matrix)
composition <- lapply(seq_along(sample_ids), function(index) list(
  sample_id = sample_ids[[index]],
  reported_sum = as.numeric(reported_sums[[index]]),
  residual_fraction = max(0, 1 - as.numeric(reported_sums[[index]])),
  within_tolerance = abs(as.numeric(reported_sums[[index]]) - 1) <= 1e-6
))
warnings <- character()
if (blank_symbol_count > 0L) warnings <- c(warnings, sprintf("Excluded %d feature(s) without a gene symbol.", blank_symbol_count))
if (duplicate_symbol_count > 0L) warnings <- c(warnings, sprintf("Collapsed %d duplicate gene-symbol row(s) by summing TPM values.", duplicate_symbol_count))
warnings <- c(warnings, "Research use only; deconvolution estimates are method- and reference-specific and are not clinical measurements.")

cell_types <- lapply(reference$cell_types, function(item) list(id = item$id, label = item$label, category = "immune_or_other"))
result <- list(
  schema_version = "1.0.0",
  analysis_id = request$analysis_id,
  prepared_dataset_id = request$prepared_dataset_id,
  method = "quantiseq",
  method_registry_version = request$method_registry_version,
  method_registry_sha256 = request$method_registry_sha256,
  result_type = "cell_fraction",
  quantity_label = request$deconvolution_method$quantity_label,
  unit = "fraction",
  composition_constraint = "sum_to_one_with_other",
  input_validation = list(
    assay = "tpm", scale = "linear", value_type = "nonnegative_continuous",
    feature_level = "gene", identifier_namespace = "gene_symbol",
    input_feature_count = nrow(expression_matrix), mapped_feature_count = nrow(symbol_matrix),
    blank_symbol_count = blank_symbol_count, duplicate_symbol_count = duplicate_symbol_count,
    reference_gene_count = length(effective_genes), overlap_gene_count = length(overlap_genes),
    overlap_fraction = overlap_fraction, minimum_overlap_fraction = minimum_overlap, passed = TRUE
  ),
  reference = list(
    id = reference$id, version = reference$version, sha256 = reference_sha256,
    cell_type_count = length(reference$cell_types)
  ),
  cell_types = cell_types,
  sample_ids = as.list(sample_ids),
  estimates = estimate_rows,
  composition_summaries = composition,
  warnings = as.list(warnings),
  software = list(
    language = "R", language_version = as.character(getRversion()),
    packages = list(quantiseqr = as.character(packageVersion("quantiseqr")), jsonlite = as.character(packageVersion("jsonlite"))),
    algorithm = list(regression = "lsei", tumor_mode = isTRUE(request$parameters$tumor_mode), scale_mrna = isTRUE(request$parameters$scale_mrna))
  ),
  provenance = list(
    expression_bundle_sha256 = bundle_sha256,
    analysis_request_sha256 = request_sha256,
    reference_sha256 = reference_sha256
  )
)
write_json(result, file.path(output_dir, "deconvolution_results.json"))

table_rows <- do.call(rbind, lapply(estimate_rows, as.data.frame, stringsAsFactors = FALSE))
write.table(table_rows, file.path(output_dir, "deconvolution_estimates.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
overlap_rows <- data.frame(
  gene_symbol = effective_genes,
  present_in_input = effective_genes %in% rownames(symbol_matrix),
  stringsAsFactors = FALSE
)
write.table(overlap_rows, file.path(output_dir, "reference_overlap.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

svg(file.path(output_dir, "cell_fractions.svg"), width = 11, height = max(5, 0.35 * length(sample_ids) + 2))
par(mar = c(5, max(8, max(nchar(sample_ids)) * 0.6), 3, 10), xpd = TRUE)
palette <- grDevices::hcl.colors(length(cell_type_ids), "Set 3")
barplot(
  t(estimate_matrix), horiz = TRUE, names.arg = sample_ids, las = 1,
  col = palette, border = NA, xlab = "Estimated cell fraction", main = "quanTIseq immune-cell composition"
)
legend("topright", inset = c(-0.32, 0), legend = cell_type_ids, fill = palette, border = NA, cex = 0.75)
dev.off()

manifest <- list(
  schema_version = "1.0.0", analysis_type = "deconvolution", title = "quanTIseq cell-type deconvolution",
  summary_metrics = list(
    list(label = "Samples", value = length(sample_ids)),
    list(label = "Cell populations", value = length(cell_type_ids)),
    list(label = "Reference overlap", value = sprintf("%.1f%%", 100 * overlap_fraction)),
    list(label = "Reference", value = reference$version)
  ),
  sections = list(list(
    id = "cell_fractions", title = "Estimated cell fractions",
    items = list(
      list(type = "image", title = "Cell-fraction composition", path = "cell_fractions.svg"),
      list(type = "table", title = "Long-format cell fractions", path = "deconvolution_estimates.tsv")
    )
  )),
  downloads = list(
    list(type = "file", title = "Structured deconvolution results", path = "deconvolution_results.json"),
    list(type = "table", title = "Reference overlap audit", path = "reference_overlap.tsv"),
    list(type = "file", title = "R session information", path = "session_info.txt"),
    list(type = "file", title = "Quarto report source", path = "report.qmd")
  ),
  warnings = as.list(warnings)
)
write_json(manifest, file.path(output_dir, "result_manifest.json"))
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))
report <- c(
  "---", "title: \"TranscriptForge quanTIseq deconvolution\"", "format:", "  html:",
  "    embed-resources: true", "---", "", "## Analysis", "",
  paste("- Samples:", length(sample_ids)), paste("- Reference:", reference$version),
  paste("- Effective signature overlap:", sprintf("%d/%d (%.1f%%)", length(overlap_genes), length(effective_genes), 100 * overlap_fraction)),
  paste("- Tumor mode:", isTRUE(request$parameters$tumor_mode)),
  paste("- Cell-type mRNA scaling:", isTRUE(request$parameters$scale_mrna)), "",
  "## Estimated composition", "", "![](cell_fractions.svg)", "",
  "## Interpretation", "",
  "Fractions include an Other / uncharacterized compartment and sum to one per sample.",
  "Results are quanTIseq/TIL10-specific research estimates, not clinical measurements.", "",
  "## Reproducibility", "", paste("- quantiseqr:", packageVersion("quantiseqr")),
  paste("- Reference manifest SHA-256:", reference_sha256),
  paste("- Analysis request SHA-256:", request_sha256),
  "- Full package and platform details: `session_info.txt`"
)
writeLines(report, file.path(output_dir, "report.qmd"))
