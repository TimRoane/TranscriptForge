#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(BiocParallel)
  library(GSVA)
  library(jsonlite)
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

safe_path <- function(root, relative) {
  if (startsWith(relative, "/") || any(strsplit(relative, "/", fixed = TRUE)[[1L]] == "..")) {
    abort(paste("Expression Bundle contains an unsafe path:", relative))
  }
  file.path(root, relative)
}

sha256_file <- function(path) {
  output <- system2("sha256sum", path, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if ((!is.null(status) && status != 0L) || length(output) != 1L) {
    abort("Unable to calculate the Expression Bundle SHA-256 checksum.")
  }
  sub("[[:space:]].*$", "", output[[1L]])
}

mapping_warnings <- function(report) {
  warnings <- character()
  for (item in list(
    c("missing", "missing_identifier_count"),
    c("ambiguous", "ambiguous_identifier_count"),
    c("duplicate", "duplicate_identifier_count")
  )) {
    count <- as.integer(report[[item[[2L]]]])
    if (count > 0L) warnings <- c(warnings, sprintf("Mapping report contains %d %s identifier(s).", count, item[[1L]]))
  }
  warnings
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("request", "bundle", "output-dir")
missing_args <- required[!required %in% names(args)]
if (length(missing_args)) abort(paste("Missing arguments:", paste(missing_args, collapse = ", ")))

request <- fromJSON(args$request, simplifyVector = FALSE)
if (!identical(request$analysis_type, "signature")) abort("Request is not signature scoring.")
if (!request$method %in% c("gsva", "ssgsea")) abort(paste("Unsupported R signature method:", request$method))
if (!identical(request$assay, "log_expression")) abort("GSVA and ssGSEA require log_expression.")
if (is.null(request$signature_mapping$report)) abort("The frozen signature mapping is missing.")

parameters <- request$parameters
if (parameters$minimum_gene_set_size > parameters$maximum_gene_set_size) {
  abort("Minimum gene-set size cannot exceed maximum gene-set size.")
}

mapping <- request$signature_mapping
mapping_report <- mapping$report
bundle_digest <- sha256_file(args$bundle)
if (!identical(bundle_digest, mapping_report$expression_bundle_sha256)) {
  abort("Expression Bundle checksum differs from the frozen mapping report.")
}

output_dir <- args$`output-dir`
if (dir.exists(output_dir)) abort(paste("Output directory already exists:", output_dir))
dir.create(output_dir, recursive = TRUE)
extract_dir <- tempfile("transcriptforge-bundle-")
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

assay_index <- which(vapply(
  bundle_manifest$assays,
  function(item) identical(item$name, request$assay),
  logical(1L)
))
if (length(assay_index) != 1L) abort(paste("Assay is missing or duplicated in bundle:", request$assay))
assay_path <- safe_path(bundle_root, bundle_manifest$assays[[assay_index]]$path)
metadata_path <- safe_path(bundle_root, bundle_manifest$sample_metadata)
if (!file.exists(assay_path) || !file.exists(metadata_path)) {
  abort("Bundle assay or sample metadata file is missing.")
}

metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
assay_frame <- read.delim(assay_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!"sample_id" %in% names(metadata)) abort("Sample metadata must contain sample_id.")
if (ncol(assay_frame) < 2L || names(assay_frame)[[1L]] != "feature_id") {
  abort("Expression assay must begin with feature_id and include sample columns.")
}
if (anyDuplicated(metadata$sample_id) || anyDuplicated(assay_frame$feature_id)) {
  abort("Bundle contains duplicate sample or feature identifiers.")
}
sample_ids <- names(assay_frame)[-1L]
if (!setequal(sample_ids, metadata$sample_id)) abort("Assay and metadata sample identifiers do not match.")
if (length(sample_ids) < 2L) abort("GSVA and ssGSEA require at least two samples.")
metadata <- metadata[match(sample_ids, metadata$sample_id), , drop = FALSE]
expression_matrix <- as.matrix(assay_frame[, -1L, drop = FALSE])
storage.mode(expression_matrix) <- "numeric"
rownames(expression_matrix) <- assay_frame$feature_id
colnames(expression_matrix) <- sample_ids
if (any(!is.finite(expression_matrix))) abort("Expression assay contains non-finite values.")

feature_index <- setNames(seq_len(nrow(expression_matrix)), rownames(expression_matrix))
variable_features <- apply(expression_matrix, 1L, function(values) stats::sd(values) > 0)
scoring_matrix <- expression_matrix[variable_features, , drop = FALSE]
gene_sets <- list()
feature_rows <- list()
set_details <- list()
warnings <- mapping_warnings(mapping_report)
row_cursor <- 1L

for (set_index in seq_along(mapping_report$sets)) {
  signature_set <- mapping_report$sets[[set_index]]
  entries <- signature_set$mapped_entries
  if (!length(entries)) abort(paste("Signature set has no mapped features:", signature_set$name))
  feature_ids <- vapply(entries, function(entry) entry$feature_id, character(1L))
  missing_features <- setdiff(feature_ids, rownames(expression_matrix))
  if (length(missing_features)) {
    abort(paste("Mapped features are absent from the selected assay:", paste(head(missing_features, 10L), collapse = ", ")))
  }
  used <- unname(variable_features[feature_ids])
  used_feature_ids <- unique(feature_ids[used])
  excluded_count <- sum(!used)
  if (excluded_count > 0L) {
    warnings <- c(warnings, sprintf(
      "%s: excluded %d constant feature(s) before %s scoring.",
      signature_set$name, excluded_count, request$method
    ))
  }
  used_count <- length(used_feature_ids)
  if (used_count < parameters$minimum_gene_set_size || used_count > parameters$maximum_gene_set_size) {
    abort(sprintf(
      "%s has %d variable mapped feature(s), outside the configured range %d-%d.",
      signature_set$name, used_count,
      parameters$minimum_gene_set_size, parameters$maximum_gene_set_size
    ))
  }
  if (any(vapply(entries, function(entry) !is.null(entry$weight), logical(1L)))) {
    warnings <- c(warnings, paste(signature_set$name, "contains weights; GSVA/ssGSEA ignores weights."))
  }
  signature_id <- signature_set$signature_id
  if (signature_id %in% names(gene_sets)) abort(paste("Duplicate signature ID:", signature_id))
  gene_sets[[signature_id]] <- used_feature_ids
  set_details[[signature_id]] <- list(source = signature_set, excluded_count = excluded_count)
  for (entry_index in seq_along(entries)) {
    entry <- entries[[entry_index]]
    feature_rows[[row_cursor]] <- data.frame(
      signature_id = signature_id,
      signature_name = signature_set$name,
      identifier = entry$identifier,
      feature_id = entry$feature_id,
      weight = if (is.null(entry$weight)) "" else format(as.numeric(entry$weight), digits = 17),
      used = if (used[[entry_index]]) "TRUE" else "FALSE",
      exclusion_reason = if (used[[entry_index]]) "" else "constant_across_samples",
      stringsAsFactors = FALSE
    )
    row_cursor <- row_cursor + 1L
  }
}

parameter_object <- if (identical(request$method, "gsva")) {
  gsvaParam(
    exprData = scoring_matrix,
    geneSets = gene_sets,
    minSize = parameters$minimum_gene_set_size,
    maxSize = parameters$maximum_gene_set_size,
    kcdf = parameters$gsva_kcdf,
    tau = parameters$gsva_tau,
    maxDiff = parameters$gsva_max_diff,
    absRanking = parameters$gsva_abs_ranking,
    sparse = FALSE,
    checkNA = "yes"
  )
} else {
  ssgseaParam(
    exprData = scoring_matrix,
    geneSets = gene_sets,
    minSize = parameters$minimum_gene_set_size,
    maxSize = parameters$maximum_gene_set_size,
    alpha = parameters$ssgsea_alpha,
    normalize = parameters$ssgsea_normalize,
    checkNA = "yes"
  )
}
score_matrix <- GSVA::gsva(
  parameter_object,
  verbose = FALSE,
  BPPARAM = BiocParallel::SerialParam(progressbar = FALSE)
)
score_matrix <- as.matrix(score_matrix)
if (!identical(colnames(score_matrix), sample_ids)) abort("GSVA returned an unexpected sample order.")
if (!setequal(rownames(score_matrix), names(gene_sets))) abort("GSVA returned unexpected signature sets.")
score_matrix <- score_matrix[names(gene_sets), sample_ids, drop = FALSE]
if (any(!is.finite(score_matrix))) abort("GSVA produced non-finite scores.")

metadata_records <- setNames(lapply(seq_along(sample_ids), function(sample_index) {
  row <- metadata[sample_index, , drop = FALSE]
  as.list(vapply(row, function(value) as.character(value[[1L]]), character(1L)))
}), sample_ids)

set_results <- lapply(names(gene_sets), function(signature_id) {
  detail <- set_details[[signature_id]]
  signature_set <- detail$source
  values <- as.numeric(score_matrix[signature_id, ])
  list(
    signature_id = signature_id,
    name = signature_set$name,
    requested_identifier_count = signature_set$requested_identifier_count,
    mapped_identifier_count = signature_set$mapped_identifier_count,
    scored_feature_count = length(gene_sets[[signature_id]]),
    excluded_constant_feature_count = detail$excluded_count,
    mapping_coverage = signature_set$mapping_coverage,
    score_minimum = min(values),
    score_maximum = max(values),
    score_mean = mean(values),
    scores = lapply(seq_along(sample_ids), function(sample_index) list(
      sample_id = sample_ids[[sample_index]],
      score = values[[sample_index]],
      metadata = metadata_records[[sample_ids[[sample_index]]]]
    ))
  )
})

formula <- if (identical(request$method, "gsva")) {
  sprintf(
    "Bioconductor GSVA enrichment scores (kcdf=%s, tau=%s, maxDiff=%s, absRanking=%s).",
    parameters$gsva_kcdf, parameters$gsva_tau,
    parameters$gsva_max_diff, parameters$gsva_abs_ranking
  )
} else {
  sprintf(
    "Bioconductor single-sample GSEA enrichment scores (alpha=%s, normalize=%s).",
    parameters$ssgsea_alpha, parameters$ssgsea_normalize
  )
}
software <- list(
  language = "R",
  language_version = R.version.string,
  implementation = "Bioconductor GSVA parameter-object API",
  packages = list(
    GSVA = as.character(packageVersion("GSVA")),
    BiocParallel = as.character(packageVersion("BiocParallel")),
    jsonlite = as.character(packageVersion("jsonlite"))
  )
)
summary <- list(
  schema_version = "1.0.0",
  analysis_id = request$analysis_id,
  prepared_dataset_id = request$prepared_dataset_id,
  method = request$method,
  assay = request$assay,
  formula = formula,
  signature_mapping = list(
    id = mapping$id,
    report_sha256 = mapping$report_sha256,
    signature_definition_id = mapping_report$signature_definition_id,
    signature_definition_sha256 = mapping_report$signature_definition_sha256,
    expression_bundle_sha256 = bundle_digest,
    mapping_coverage = mapping_report$mapping_coverage,
    requested_identifier_count = mapping_report$requested_identifier_count,
    mapped_identifier_count = mapping_report$mapped_identifier_count,
    missing_identifier_count = mapping_report$missing_identifier_count,
    ambiguous_identifier_count = mapping_report$ambiguous_identifier_count,
    duplicate_identifier_count = mapping_report$duplicate_identifier_count
  ),
  sample_count = length(sample_ids),
  set_count = length(set_results),
  sets = set_results,
  warnings = as.list(unique(warnings)),
  software = software
)
write_json(summary, file.path(output_dir, "signature_scores.json"))

score_rows <- do.call(rbind, lapply(set_results, function(signature_set) {
  data.frame(
    sample_id = vapply(signature_set$scores, function(item) item$sample_id, character(1L)),
    signature_id = signature_set$signature_id,
    signature_name = signature_set$name,
    score = vapply(signature_set$scores, function(item) item$score, numeric(1L)),
    stringsAsFactors = FALSE
  )
}))
write.table(score_rows, file.path(output_dir, "signature_scores.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write.table(do.call(rbind, feature_rows), file.path(output_dir, "scored_features.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

colors <- c("#155e75", "#7c3aed", "#d97706", "#be123c", "#15803d")
svg(file.path(output_dir, "signature_scores.svg"), width = 10, height = 6, bg = "white")
matplot(
  t(score_matrix), type = "b", pch = 16L, lty = 1L,
  col = rep(colors, length.out = nrow(score_matrix)), xaxt = "n",
  xlab = "Samples", ylab = "Enrichment score", main = "Per-sample signature scores"
)
axis(1L, at = seq_along(sample_ids), labels = sample_ids, las = 2L, cex.axis = 0.7)
legend(
  "topright", legend = vapply(set_results, function(item) item$name, character(1L)),
  col = rep(colors, length.out = nrow(score_matrix)), pch = 16L, lty = 1L, cex = 0.75
)
dev.off()

manifest <- list(
  schema_version = "1.0.0",
  analysis_type = "signature",
  title = paste("Signature scoring:", request$method),
  summary_metrics = list(
    list(label = "Samples", value = length(sample_ids)),
    list(label = "Signature sets", value = length(set_results)),
    list(label = "Method", value = request$method),
    list(label = "Mapping coverage", value = mapping_report$mapping_coverage),
    list(label = "Mapped identifiers", value = mapping_report$mapped_identifier_count),
    list(label = "Missing identifiers", value = mapping_report$missing_identifier_count)
  ),
  sections = list(list(
    id = "signature-scores", title = "Per-sample signature scores",
    items = list(
      list(type = "plotly_json", title = "Signature scores", path = "signature_scores.json"),
      list(type = "image", title = "Static signature scores", path = "signature_scores.svg"),
      list(type = "table", title = "Per-sample scores", path = "signature_scores.tsv")
    )
  )),
  downloads = list(
    list(type = "table", title = "Per-sample scores", path = "signature_scores.tsv"),
    list(type = "table", title = "Final scored features", path = "scored_features.tsv"),
    list(type = "image", title = "Signature scores (SVG)", path = "signature_scores.svg"),
    list(type = "html", title = "Signature report", path = "report.html"),
    list(type = "file", title = "Quarto report source", path = "report.qmd")
  ),
  warnings = as.list(unique(warnings))
)
write_json(manifest, file.path(output_dir, "result_manifest.json"))
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))

report <- c(
  "---", "title: \"TranscriptForge signature scoring\"", "format:", "  html:",
  "    embed-resources: true", "---", "", "## Analysis", "",
  paste("- Method:", request$method),
  paste("- Assay:", request$assay),
  paste("- Samples:", length(sample_ids)),
  paste("- Signature sets:", length(set_results)),
  paste("- Mapping coverage:", sprintf("%.1f%%", 100 * mapping_report$mapping_coverage)),
  paste("- Formula:", formula), "", "## Scores", "", "![](signature_scores.svg)", "",
  "## Interpretation", "",
  "Scores are exploratory, cohort- and assay-dependent, and are not clinically validated.",
  "Mapping coverage and the final scored-feature table must accompany interpretation.", "",
  "## Reproducibility", "", paste("- R:", software$language_version),
  paste("- GSVA:", software$packages$GSVA),
  paste("- BiocParallel:", software$packages$BiocParallel),
  "- Full package and platform details: `session_info.txt`"
)
writeLines(report, file.path(output_dir, "report.qmd"))
