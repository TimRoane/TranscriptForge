#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

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

same_value <- function(left, right) {
  identical(left, right) || identical(as.character(left), as.character(right))
}

load_package_object <- function(package_name, object_name) {
  environment <- new.env(parent = emptyenv())
  suppressWarnings(utils::data(list = object_name, package = package_name, envir = environment))
  if (!exists(object_name, envir = environment, inherits = FALSE)) {
    abort(paste("Pinned package object is unavailable:", object_name))
  }
  get(object_name, envir = environment, inherits = FALSE)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("request", "bundle", "reference-manifest", "output-dir")
missing_args <- required[!required %in% names(args)]
if (length(missing_args)) abort(paste("Missing arguments:", paste(missing_args, collapse = ", ")))

request <- fromJSON(args$request, simplifyVector = FALSE)
reference <- fromJSON(args$`reference-manifest`, simplifyVector = FALSE)
supported_methods <- c("quantiseq", "mcp_counter", "xcell")
if (!identical(request$analysis_type, "deconvolution")) abort("Request is not deconvolution.")
if (!request$method %in% supported_methods) abort(paste("Unsupported deconvolution method:", request$method))
if (!identical(reference$method, request$method) ||
    !identical(reference$id, request$parameters$reference_profile)) {
  abort("Reference manifest differs from the frozen method/reference request.")
}
if (!identical(request$deconvolution_method$id, request$method) ||
    !identical(request$deconvolution_method$result_type, if (request$method == "quantiseq") "cell_fraction" else "enrichment_score")) {
  abort("Frozen deconvolution method semantics do not match the requested runner.")
}
package_name <- reference$package$name
if (!requireNamespace(package_name, quietly = TRUE)) abort(paste("Required package is unavailable:", package_name))
if (!identical(as.character(packageVersion(package_name)), reference$package$version)) {
  abort(paste("Installed", package_name, "version differs from the pinned reference manifest."))
}

reference_sha256 <- sha256_file(args$`reference-manifest`)
request_sha256 <- sha256_file(args$request)
bundle_sha256 <- sha256_file(args$bundle)
if (is.null(request$expression_bundle$sha256) || !identical(bundle_sha256, request$expression_bundle$sha256)) {
  abort("Expression Bundle checksum differs from the frozen analysis request.")
}

package_objects <- list()
for (item in reference$files) {
  observed_sha256 <- NULL
  label <- NULL
  if (!is.null(item$package_path)) {
    relative <- sub("^extdata/", "", item$package_path)
    installed_path <- system.file("extdata", relative, package = package_name, mustWork = TRUE)
    observed_sha256 <- sha256_file(installed_path)
    label <- item$package_path
  } else if (!is.null(item$runtime_path)) {
    if (!file.exists(item$runtime_path)) abort(paste("Pinned runtime reference is missing:", item$runtime_path))
    observed_sha256 <- sha256_file(item$runtime_path)
    label <- item$runtime_path
  } else if (!is.null(item$package_object)) {
    if (!requireNamespace("digest", quietly = TRUE)) abort("digest is required to audit package objects.")
    package_objects[[item$package_object]] <- load_package_object(package_name, item$package_object)
    observed_sha256 <- digest::digest(package_objects[[item$package_object]], algo = "sha256", serialize = TRUE)
    label <- item$package_object
  }
  if (is.null(observed_sha256) || !identical(observed_sha256, item$sha256)) {
    abort(paste("Installed reference checksum differs for", label))
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

assay_index <- which(vapply(bundle_manifest$assays, function(item) identical(item$name, request$assay), logical(1L)))
if (length(assay_index) != 1L) abort("Requested assay is missing or duplicated in the bundle.")
assay_descriptor <- bundle_manifest$assays[[assay_index]]
for (field in c("name", "scale", "value_type", "feature_level", "sha256")) {
  if (!same_value(assay_descriptor[[field]], request$input_assay_descriptor[[field]])) {
    abort(paste("Bundle assay descriptor differs from frozen request field:", field))
  }
}
assay_options <- Filter(function(item) identical(item$name, request$assay), request$deconvolution_method$input$assay_options)
if (length(assay_options) != 1L ||
    !assay_descriptor$scale %in% unlist(assay_options[[1L]]$scales) ||
    !assay_descriptor$value_type %in% unlist(assay_options[[1L]]$value_types) ||
    !identical(assay_descriptor$feature_level, "gene")) {
  abort("Assay scale/value type is incompatible with the frozen deconvolution method.")
}

assay_path <- safe_path(bundle_root, assay_descriptor$path)
metadata_path <- safe_path(bundle_root, bundle_manifest$sample_metadata)
feature_metadata_path <- safe_path(bundle_root, bundle_manifest$feature_metadata)
if (!all(file.exists(c(assay_path, metadata_path, feature_metadata_path)))) {
  abort("Bundle assay, sample metadata, or feature metadata is missing.")
}
if (!identical(sha256_file(assay_path), assay_descriptor$sha256)) {
  abort("Assay checksum differs from the bundle manifest.")
}

metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
feature_metadata <- read.delim(feature_metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
assay_frame <- read.delim(assay_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!"sample_id" %in% names(metadata) || anyDuplicated(metadata$sample_id)) {
  abort("Sample metadata must contain unique sample_id values.")
}
if (ncol(assay_frame) < 2L || names(assay_frame)[[1L]] != "feature_id" || anyDuplicated(assay_frame$feature_id)) {
  abort("Assay must begin with unique feature_id values and contain sample columns.")
}
if (!all(c("feature_id", "gene_symbol") %in% names(feature_metadata)) || anyDuplicated(feature_metadata$feature_id)) {
  abort("Feature metadata must contain unique feature_id and gene_symbol columns.")
}
sample_ids <- names(assay_frame)[-1L]
if (!identical(sample_ids, as.character(metadata$sample_id))) {
  abort("Assay and metadata sample identifiers/order do not match.")
}
expression_matrix <- as.matrix(assay_frame[, -1L, drop = FALSE])
storage.mode(expression_matrix) <- "numeric"
rownames(expression_matrix) <- assay_frame$feature_id
colnames(expression_matrix) <- sample_ids
if (any(!is.finite(expression_matrix))) abort("Assay contains non-finite values.")
if (!isTRUE(request$deconvolution_method$input$negative_values_permitted) && any(expression_matrix < 0)) {
  abort(paste(request$deconvolution_method$display_name, "does not permit negative assay values."))
}

feature_metadata <- feature_metadata[match(rownames(expression_matrix), feature_metadata$feature_id), , drop = FALSE]
if (any(is.na(feature_metadata$feature_id))) abort("Assay features are missing from feature metadata.")
symbols <- trimws(as.character(feature_metadata$gene_symbol))
mapped <- !is.na(symbols) & nzchar(symbols)
blank_symbol_count <- sum(!mapped)
mapped_symbols <- symbols[mapped]
duplicate_symbol_count <- sum(duplicated(mapped_symbols))
symbol_matrix <- rowsum(expression_matrix[mapped, , drop = FALSE], mapped_symbols, reorder = FALSE)
duplicate_rule <- "sum"
if (request$method != "quantiseq") {
  counts <- table(mapped_symbols)
  symbol_matrix <- sweep(symbol_matrix, 1L, as.numeric(counts[rownames(symbol_matrix)]), "/")
  duplicate_rule <- "mean"
}
if (!nrow(symbol_matrix)) abort("No assay features have usable gene symbols.")

expected_cell_types <- vapply(reference$cell_types, function(item) item$id, character(1L))
algorithm <- list()
if (request$method == "quantiseq") {
  signature_path <- system.file("extdata", "TIL10_signature.txt", package = "quantiseqr", mustWork = TRUE)
  signature <- read.delim(signature_path, check.names = FALSE, row.names = 1)
  if (nrow(signature) != reference$signature_gene_count) {
    abort("quanTIseq signature gene count differs from the pinned manifest.")
  }
  effective_genes <- rownames(signature)
  rm_genes_path <- system.file("extdata", "TIL10_rmgenes.txt", package = "quantiseqr", mustWork = TRUE)
  effective_genes <- setdiff(effective_genes, readLines(rm_genes_path, warn = FALSE))
  if (isTRUE(request$parameters$tumor_mode)) {
    tumor_path <- system.file("extdata", "TIL10_TCGA_aberrant_immune_genes.txt", package = "quantiseqr", mustWork = TRUE)
    effective_genes <- setdiff(effective_genes, readLines(tumor_path, warn = FALSE))
  }
} else if (request$method == "mcp_counter") {
  marker_path <- reference$files[[1L]]$runtime_path
  marker_frame <- read.delim(marker_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!all(c("HUGO symbols", "Cell population") %in% names(marker_frame))) {
    abort("MCP-counter marker reference has unexpected columns.")
  }
  effective_genes <- unique(marker_frame[["HUGO symbols"]])
} else {
  xcell_data <- package_objects[["xCell.data"]]
  if (is.null(xcell_data)) xcell_data <- load_package_object("xCell", "xCell.data")
  effective_genes <- as.character(xcell_data$genes)
  if (!identical(rownames(xcell_data$spill$K), expected_cell_types)) {
    abort("Installed xCell population reference differs from the pinned manifest.")
  }
}
if (request$method != "quantiseq" && length(effective_genes) != reference$signature_gene_count) {
  abort("Effective reference gene count differs from the pinned manifest.")
}
overlap_genes <- intersect(effective_genes, rownames(symbol_matrix))
overlap_fraction <- length(overlap_genes) / length(effective_genes)
minimum_overlap <- as.numeric(request$parameters$minimum_gene_overlap)
if (!is.finite(minimum_overlap) || minimum_overlap < 0 || minimum_overlap > 1) {
  abort("minimum_gene_overlap must be between zero and one.")
}
if (overlap_fraction < minimum_overlap) {
  abort(sprintf(
    "%s reference overlap %.1f%% is below the frozen minimum %.1f%% (%d/%d genes).",
    request$deconvolution_method$display_name, 100 * overlap_fraction, 100 * minimum_overlap,
    length(overlap_genes), length(effective_genes)
  ))
}

if (request$method == "quantiseq") {
  raw_results <- quantiseqr::run_quantiseq(
    expression_data = symbol_matrix, signature_matrix = "TIL10", is_arraydata = FALSE,
    is_tumordata = isTRUE(request$parameters$tumor_mode),
    scale_mRNA = isTRUE(request$parameters$scale_mrna), method = "lsei",
    rm_genes = "default", return_se = FALSE
  )
  if (!identical(as.character(raw_results$Sample), sample_ids)) abort("quanTIseq returned an unexpected sample order.")
  cell_type_ids <- names(raw_results)[-1L]
  estimate_matrix <- as.matrix(raw_results[, -1L, drop = FALSE])
  algorithm <- list(regression = "lsei", tumor_mode = isTRUE(request$parameters$tumor_mode), scale_mrna = isTRUE(request$parameters$scale_mrna))
} else if (request$method == "mcp_counter") {
  raw_results <- MCPcounter::MCPcounter.estimate(
    symbol_matrix, featuresType = "HUGO_symbols", genes = marker_frame
  )
  if (!setequal(rownames(raw_results), expected_cell_types)) abort("MCP-counter returned unexpected populations.")
  raw_results <- raw_results[expected_cell_types, sample_ids, drop = FALSE]
  estimate_matrix <- t(as.matrix(raw_results))
  cell_type_ids <- colnames(estimate_matrix)
  algorithm <- list(summary_statistic = "mean_marker_expression", features_type = "HUGO_symbols")
} else {
  is_rnaseq <- is.null(bundle_manifest$microarray)
  raw_results <- xCell::xCellAnalysis(
    symbol_matrix, signatures = xcell_data$signatures, genes = xcell_data$genes,
    spill = if (is_rnaseq) xcell_data$spill else xcell_data$spill.array,
    rnaseq = is_rnaseq, parallel.sz = 1L, cell.types.use = expected_cell_types
  )
  if (!is.matrix(raw_results) || !setequal(rownames(raw_results), expected_cell_types)) {
    abort("xCell returned unexpected populations.")
  }
  raw_results <- raw_results[expected_cell_types, sample_ids, drop = FALSE]
  estimate_matrix <- t(as.matrix(raw_results))
  cell_type_ids <- colnames(estimate_matrix)
  algorithm <- list(pipeline = "ssGSEA_transform_spillover", platform = if (is_rnaseq) "RNA-seq" else "microarray", parallel_workers = 1L)
}
storage.mode(estimate_matrix) <- "numeric"
if (!identical(cell_type_ids, expected_cell_types)) abort("Runner returned an unexpected population order.")
if (!identical(rownames(estimate_matrix), sample_ids)) abort("Runner returned an unexpected sample order.")
if (any(!is.finite(estimate_matrix))) abort("Runner returned non-finite estimates.")
if (request$method == "quantiseq" && any(estimate_matrix < -1e-12)) abort("quanTIseq returned negative fractions.")
if (request$method == "quantiseq") estimate_matrix[estimate_matrix < 0] <- 0

estimate_rows <- list()
cursor <- 1L
for (sample_index in seq_along(sample_ids)) {
  for (cell_index in seq_along(cell_type_ids)) {
    estimate_rows[[cursor]] <- list(
      sample_id = sample_ids[[sample_index]], cell_type_id = cell_type_ids[[cell_index]],
      value = as.numeric(estimate_matrix[sample_index, cell_index])
    )
    cursor <- cursor + 1L
  }
}
warnings <- character()
if (blank_symbol_count > 0L) warnings <- c(warnings, sprintf("Excluded %d feature(s) without a gene symbol.", blank_symbol_count))
if (duplicate_symbol_count > 0L) warnings <- c(warnings, sprintf("Collapsed %d duplicate gene-symbol row(s) using the %s rule for %s input.", duplicate_symbol_count, duplicate_rule, assay_descriptor$scale))
if (request$method != "quantiseq") {
  warnings <- c(warnings, "Enrichment scores are arbitrary, non-compositional units. Compare the same population between samples; do not convert scores to percentages or compare magnitudes across populations within a sample.")
}
warnings <- c(warnings, "Research use only; cell-population estimates are method- and reference-specific and are not clinical measurements.")

cell_types <- lapply(reference$cell_types, function(item) list(id = item$id, label = item$label, category = "cell_population"))
result <- list(
  schema_version = "1.0.0", analysis_id = request$analysis_id,
  prepared_dataset_id = request$prepared_dataset_id, method = request$method,
  method_registry_version = request$method_registry_version,
  method_registry_sha256 = request$method_registry_sha256,
  result_type = request$deconvolution_method$result_type,
  quantity_label = request$deconvolution_method$quantity_label,
  unit = request$deconvolution_method$unit,
  composition_constraint = request$deconvolution_method$composition_constraint,
  input_validation = list(
    assay = assay_descriptor$name, scale = assay_descriptor$scale, value_type = assay_descriptor$value_type,
    feature_level = "gene", identifier_namespace = "gene_symbol",
    input_feature_count = nrow(expression_matrix), mapped_feature_count = nrow(symbol_matrix),
    blank_symbol_count = blank_symbol_count, duplicate_symbol_count = duplicate_symbol_count,
    reference_gene_count = length(effective_genes), overlap_gene_count = length(overlap_genes),
    overlap_fraction = overlap_fraction, minimum_overlap_fraction = minimum_overlap, passed = TRUE
  ),
  reference = list(id = reference$id, version = reference$version, sha256 = reference_sha256, cell_type_count = length(reference$cell_types)),
  cell_types = cell_types, sample_ids = as.list(sample_ids), estimates = estimate_rows,
  warnings = as.list(warnings),
  software = list(
    language = "R", language_version = as.character(getRversion()),
    packages = setNames(list(as.character(packageVersion(package_name)), as.character(packageVersion("jsonlite"))), c(package_name, "jsonlite")),
    algorithm = algorithm
  ),
  provenance = list(expression_bundle_sha256 = bundle_sha256, analysis_request_sha256 = request_sha256, reference_sha256 = reference_sha256)
)
if (request$method == "quantiseq") {
  reported_sums <- rowSums(estimate_matrix)
  result$composition_summaries <- lapply(seq_along(sample_ids), function(index) list(
    sample_id = sample_ids[[index]], reported_sum = as.numeric(reported_sums[[index]]),
    residual_fraction = max(0, 1 - as.numeric(reported_sums[[index]])),
    within_tolerance = abs(as.numeric(reported_sums[[index]]) - 1) <= 1e-6
  ))
}
write_json(result, file.path(output_dir, "deconvolution_results.json"))

table_rows <- do.call(rbind, lapply(estimate_rows, as.data.frame, stringsAsFactors = FALSE))
write.table(table_rows, file.path(output_dir, "deconvolution_estimates.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
overlap_rows <- data.frame(gene_symbol = effective_genes, present_in_input = effective_genes %in% rownames(symbol_matrix), stringsAsFactors = FALSE)
write.table(overlap_rows, file.path(output_dir, "reference_overlap.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

if (request$method == "quantiseq") {
  plot_path <- "cell_fractions.svg"
  plot_title <- "Estimated cell fractions"
  svg(file.path(output_dir, plot_path), width = 11, height = max(5, 0.35 * length(sample_ids) + 2))
  par(mar = c(5, max(8, max(nchar(sample_ids)) * 0.6), 3, 10), xpd = TRUE)
  palette <- grDevices::hcl.colors(length(cell_type_ids), "Set 3")
  barplot(t(estimate_matrix), horiz = TRUE, names.arg = sample_ids, las = 1, col = palette, border = NA, xlab = "Estimated cell fraction", main = "quanTIseq immune-cell composition")
  legend("topright", inset = c(-0.32, 0), legend = cell_type_ids, fill = palette, border = NA, cex = 0.75)
  dev.off()
} else {
  plot_path <- "enrichment_scores.svg"
  plot_title <- "Within-population enrichment pattern"
  variances <- apply(estimate_matrix, 2L, stats::var)
  variances[!is.finite(variances)] <- 0
  selected <- order(variances, decreasing = TRUE)[seq_len(min(20L, length(variances)))]
  z_scores <- apply(estimate_matrix[, selected, drop = FALSE], 2L, function(values) {
    deviation <- stats::sd(values)
    if (!is.finite(deviation) || deviation == 0) rep(0, length(values)) else (values - mean(values)) / deviation
  })
  if (is.null(dim(z_scores))) z_scores <- matrix(z_scores, ncol = 1L)
  colnames(z_scores) <- cell_type_ids[selected]
  rownames(z_scores) <- sample_ids
  svg(file.path(output_dir, plot_path), width = max(9, 0.55 * length(sample_ids) + 5), height = max(6, 0.32 * ncol(z_scores) + 2))
  par(mar = c(max(7, max(nchar(sample_ids)) * 0.55), max(8, max(nchar(colnames(z_scores))) * 0.55), 3, 2))
  image(seq_len(nrow(z_scores)), seq_len(ncol(z_scores)), z_scores, col = hcl.colors(101, "Blue-Red 3"), axes = FALSE, xlab = "", ylab = "", main = paste(request$deconvolution_method$display_name, "within-population z-scores"))
  axis(1, at = seq_len(nrow(z_scores)), labels = sample_ids, las = 2, cex.axis = 0.75)
  axis(2, at = seq_len(ncol(z_scores)), labels = colnames(z_scores), las = 2, cex.axis = 0.7)
  box()
  dev.off()
}

manifest <- list(
  schema_version = "1.0.0", analysis_type = "deconvolution",
  title = paste(request$deconvolution_method$display_name, "cell-population analysis"),
  summary_metrics = list(
    list(label = "Samples", value = length(sample_ids)),
    list(label = "Cell populations", value = length(cell_type_ids)),
    list(label = "Reference overlap", value = sprintf("%.1f%%", 100 * overlap_fraction)),
    list(label = "Reference", value = reference$version)
  ),
  sections = list(list(
    id = if (request$method == "quantiseq") "cell_fractions" else "enrichment_scores",
    title = plot_title,
    items = list(
      list(type = "image", title = plot_title, path = plot_path),
      list(type = "table", title = paste("Long-format", request$deconvolution_method$quantity_label), path = "deconvolution_estimates.tsv")
    )
  )),
  downloads = list(
    list(type = "file", title = "Structured deconvolution results", path = "deconvolution_results.json"),
    list(type = "table", title = "Reference overlap audit", path = "reference_overlap.tsv"),
    list(type = "file", title = "R session information", path = "session_info.txt"),
    list(type = "file", title = "Quarto report source", path = "report.qmd")
  ), warnings = as.list(warnings)
)
write_json(manifest, file.path(output_dir, "result_manifest.json"))
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))
interpretation <- if (request$method == "quantiseq") {
  "Fractions include an Other / uncharacterized compartment and sum to one per sample."
} else {
  "Scores are non-compositional arbitrary units. Compare one population across samples; do not read them as percentages or compare different populations within a sample."
}
report <- c(
  "---", paste0("title: \"TranscriptForge ", request$deconvolution_method$display_name, " analysis\""),
  "format:", "  html:", "    embed-resources: true", "---", "", "## Analysis", "",
  paste("- Samples:", length(sample_ids)), paste("- Reference:", reference$version),
  paste("- Effective reference overlap:", sprintf("%d/%d (%.1f%%)", length(overlap_genes), length(effective_genes), 100 * overlap_fraction)),
  paste("- Result type:", request$deconvolution_method$result_type), "", paste0("## ", plot_title), "",
  paste0("![](", plot_path, ")"), "", "## Interpretation", "", interpretation,
  "Results are research-use estimates, not clinical measurements.", "", "## Reproducibility", "",
  paste0("- ", package_name, ": ", packageVersion(package_name)),
  paste("- Reference manifest SHA-256:", reference_sha256),
  paste("- Analysis request SHA-256:", request_sha256),
  "- Full package and platform details: `session_info.txt`"
)
writeLines(report, file.path(output_dir, "report.qmd"))
