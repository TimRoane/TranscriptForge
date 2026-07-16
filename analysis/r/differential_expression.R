#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(DESeq2)
  library(edgeR)
  library(limma)
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
  writeLines(toJSON(value, auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 12), path)
}

safe_path <- function(root, relative) {
  if (startsWith(relative, "/") || any(strsplit(relative, "/", fixed = TRUE)[[1L]] == "..")) {
    abort(paste("Expression Bundle contains an unsafe path:", relative))
  }
  file.path(root, relative)
}

formula_text <- function(design) {
  terms <- c(if (!is.null(design$block_column)) design$block_column else character(),
             unlist(design$covariates), design$primary_variable)
  terms <- terms[!duplicated(terms)]
  interactions <- design$interaction_terms
  interaction_variables <- unique(unlist(interactions))
  components <- terms[!terms %in% interaction_variables]
  if (length(interactions)) {
    components <- c(components, vapply(interactions, function(pair) {
      paste(pair[[1L]], "*", pair[[2L]])
    }, character(1L)))
  }
  paste("~", paste(components, collapse = " + "))
}

factor_variables <- function(design, contrast) {
  unique(c(design$primary_variable, design$block_column, contrast$variable,
           names(design$reference_levels), unlist(design$interaction_terms)))
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("request", "bundle", "output-dir")
missing_args <- required[!required %in% names(args)]
if (length(missing_args)) abort(paste("Missing arguments:", paste(missing_args, collapse = ", ")))

request <- fromJSON(args$request, simplifyVector = FALSE)
if (!identical(request$analysis_type, "differential_expression")) abort("Request is not differential expression.")
supported_methods <- c("deseq2", "edger_ql", "limma_voom", "limma")
count_methods <- c("deseq2", "edger_ql", "limma_voom")
if (!request$method %in% supported_methods) abort(paste("Unsupported R runner method:", request$method))
if (request$method %in% count_methods && !identical(request$assay, "raw_counts")) {
  abort(paste(request$method, "requires the raw_counts assay."))
}
if (identical(request$method, "limma") && identical(request$assay, "raw_counts")) {
  abort("limma requires a continuous log-scale expression assay.")
}

output_dir <- args$`output-dir`
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
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

assay_entries <- bundle_manifest$assays
assay_index <- which(vapply(assay_entries, function(item) identical(item$name, request$assay), logical(1L)))
if (length(assay_index) != 1L) abort(paste("Assay is missing or duplicated in bundle:", request$assay))
assay_path <- safe_path(bundle_root, assay_entries[[assay_index]]$path)
metadata_path <- safe_path(bundle_root, bundle_manifest$sample_metadata)
feature_metadata_path <- safe_path(bundle_root, bundle_manifest$feature_metadata)
if (!file.exists(assay_path) || !file.exists(metadata_path) || !file.exists(feature_metadata_path)) {
  abort("Bundle assay, sample metadata, or feature metadata file is missing.")
}

metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character())
feature_metadata <- read.delim(
  feature_metadata_path, check.names = FALSE, stringsAsFactors = FALSE, na.strings = character()
)
assay_frame <- read.delim(assay_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!"sample_id" %in% names(metadata)) abort("Sample metadata must contain sample_id.")
if (ncol(assay_frame) < 2L || names(assay_frame)[[1L]] != "feature_id") {
  abort("Expression assay must begin with feature_id and include sample columns.")
}
if (anyDuplicated(metadata$sample_id) || anyDuplicated(assay_frame$feature_id)) {
  abort("Bundle contains duplicate sample or feature identifiers.")
}
if (!all(c("feature_id", "gene_symbol") %in% names(feature_metadata)) ||
    anyDuplicated(feature_metadata$feature_id)) {
  abort("Feature metadata must contain unique feature_id and gene_symbol columns.")
}
sample_ids <- names(assay_frame)[-1L]
if (!setequal(sample_ids, metadata$sample_id)) abort("Assay and metadata sample identifiers do not match.")
metadata <- metadata[match(sample_ids, metadata$sample_id), , drop = FALSE]
rownames(metadata) <- metadata$sample_id
expression_matrix <- as.matrix(assay_frame[, -1L, drop = FALSE])
storage.mode(expression_matrix) <- "numeric"
rownames(expression_matrix) <- assay_frame$feature_id
if (any(!is.finite(expression_matrix))) abort("Expression assay contains non-finite values.")
if (request$method %in% count_methods &&
    (any(expression_matrix < 0) || any(expression_matrix != round(expression_matrix)))) {
  abort(paste(request$method, "input must contain nonnegative integer counts."))
}
if (request$method %in% count_methods) storage.mode(expression_matrix) <- "integer"

parameters <- request$parameters
design <- parameters$design
contrast <- parameters$contrast
variables <- unique(c(design$block_column, unlist(design$covariates), design$primary_variable,
                      unlist(design$interaction_terms)))
variables <- variables[!is.na(variables) & nzchar(variables)]
unknown <- setdiff(variables, names(metadata))
if (length(unknown)) abort(paste("R-side design references missing metadata:", paste(unknown, collapse = ", ")))
for (variable in variables) {
  values <- metadata[[variable]]
  if (any(is.na(values)) || any(trimws(as.character(values)) == "")) abort(paste("Design variable has missing values:", variable))
  if (length(unique(values)) < 2L) abort(paste("Design variable has only one observed value:", variable))
}

categorical <- unique(c(
  intersect(factor_variables(design, contrast), names(metadata)),
  variables[vapply(metadata[variables], function(values) !is.numeric(values), logical(1L))]
))
for (variable in categorical) {
  metadata[[variable]] <- factor(metadata[[variable]], levels = sort(unique(as.character(metadata[[variable]]))))
}
if (length(design$reference_levels)) {
  for (variable in names(design$reference_levels)) {
    reference <- design$reference_levels[[variable]]
    if (!reference %in% levels(metadata[[variable]])) abort(paste("Reference level is absent:", reference, "in", variable))
    metadata[[variable]] <- relevel(metadata[[variable]], ref = reference)
  }
}
if (!contrast$denominator %in% levels(metadata[[contrast$variable]])) abort("Contrast denominator is absent.")
if (!contrast$numerator %in% levels(metadata[[contrast$variable]])) abort("Contrast numerator is absent.")
metadata[[contrast$variable]] <- relevel(metadata[[contrast$variable]], ref = contrast$denominator)
contrast_counts <- table(metadata[[contrast$variable]])
if (contrast_counts[[contrast$numerator]] < parameters$minimum_samples ||
    contrast_counts[[contrast$denominator]] < parameters$minimum_samples) {
  abort("R-side contrast replication is below minimum_samples.")
}

generated_formula <- formula_text(design)
if (!identical(generated_formula, request$design_formula)) {
  abort(paste("R-side formula disagrees with frozen server preview:", generated_formula, "!=", request$design_formula))
}
model_formula <- as.formula(generated_formula)
design_matrix <- model.matrix(model_formula, metadata)
design_rank <- qr(design_matrix)$rank
expected <- request$design_validation
if (nrow(design_matrix) != expected$sample_count || design_rank != expected$design_matrix_rank ||
    ncol(design_matrix) != length(expected$design_matrix_columns)) {
  abort(sprintf("R-side design disagrees with server preview (samples %d/%d, rank %d/%d, columns %d/%d).",
                nrow(design_matrix), expected$sample_count, design_rank, expected$design_matrix_rank,
                ncol(design_matrix), length(expected$design_matrix_columns)))
}
if (design_rank < ncol(design_matrix)) abort("R-side design matrix is rank deficient.")

runner_warnings <- unlist(expected$warnings)
features_input <- nrow(expression_matrix)
features_filtered <- 0L
method_label <- switch(
  request$method,
  deseq2 = "DESeq2",
  edger_ql = "edgeR QL",
  limma_voom = "limma-voom",
  limma = "limma"
)
independent_filtering_applied <- FALSE
shrinkage_applied <- FALSE
normalization_method <- if (identical(request$method, "deseq2")) {
  "DESeq2 median-of-ratios size factors"
} else if (request$method %in% c("edger_ql", "limma_voom")) {
  "edgeR TMM normalization"
} else {
  "Input log-expression scale"
}
test_statistic <- switch(
  request$method,
  deseq2 = "Wald statistic",
  edger_ql = "quasi-likelihood F statistic",
  limma_voom = "moderated t statistic",
  limma = "moderated t statistic"
)

contrast_weights <- NULL
if (!identical(request$method, "deseq2")) {
  reference_rows <- metadata[rep(1L, 2L), , drop = FALSE]
  for (variable in variables) {
    if (is.factor(metadata[[variable]])) {
      reference_rows[[variable]] <- factor(
        rep(levels(metadata[[variable]])[[1L]], 2L), levels = levels(metadata[[variable]])
      )
    } else if (is.numeric(metadata[[variable]])) {
      reference_rows[[variable]] <- rep(mean(metadata[[variable]]), 2L)
    }
  }
  reference_rows[[contrast$variable]] <- factor(
    c(contrast$numerator, contrast$denominator), levels = levels(metadata[[contrast$variable]])
  )
  contrast_rows <- model.matrix(model_formula, reference_rows)
  contrast_weights <- contrast_rows[1L, ] - contrast_rows[2L, ]
  if (!identical(names(contrast_weights), colnames(design_matrix))) {
    abort(paste(method_label, "contrast columns do not match the validated design matrix."))
  }
  if (!any(contrast_weights != 0)) {
    abort(paste(method_label, "contrast produced an all-zero coefficient vector."))
  }
}

if (identical(request$method, "deseq2")) {
  keep <- rowSums(expression_matrix >= parameters$low_count_threshold) >= parameters$minimum_samples
  if (!any(keep)) abort("No features remain after low-count filtering.")
  filtered_counts <- expression_matrix[keep, , drop = FALSE]
  features_filtered <- sum(!keep)

  dds <- DESeqDataSetFromMatrix(countData = filtered_counts, colData = metadata, design = model_formula)
  dds <- DESeq(dds, quiet = TRUE)
  contrast_vector <- c(contrast$variable, contrast$numerator, contrast$denominator)
  result <- results(dds, contrast = contrast_vector, alpha = parameters$fdr_threshold,
                    independentFiltering = parameters$independent_filtering)
  independent_filtering_applied <- isTRUE(parameters$independent_filtering)
  if (isTRUE(parameters$shrinkage)) {
    result <- tryCatch(
      lfcShrink(dds, contrast = contrast_vector, res = result, type = "normal", quiet = TRUE),
      error = function(error) {
        runner_warnings <<- c(
          runner_warnings,
          paste("Log2-fold-change shrinkage failed; unshrunk estimates were retained:", conditionMessage(error))
        )
        results(dds, contrast = contrast_vector, alpha = parameters$fdr_threshold,
                independentFiltering = parameters$independent_filtering)
      }
    )
    shrinkage_applied <- !any(grepl("shrinkage failed", runner_warnings, fixed = TRUE))
  }
  heatmap_expression <- log2(counts(dds, normalized = TRUE) + 1)
  heatmap_source <- "log2 DESeq2 normalized count + 1"
  table <- data.frame(
    feature_id = rownames(result), base_mean = result$baseMean,
    log2_fold_change = result$log2FoldChange, standard_error = result$lfcSE,
    statistic = result$stat, p_value = result$pvalue, adjusted_p_value = result$padj,
    stringsAsFactors = FALSE, check.names = FALSE
  )
  abundance <- table$base_mean
  ma_x <- log10(abundance + 1)
  ma_x_label <- "log10 mean normalized count + 1"
} else if (identical(request$method, "edger_ql")) {
  runner_warnings <- c(
    runner_warnings,
    "edgeR QL uses the configured explicit low-count filter and TMM normalization; DESeq2 independent filtering and fold-change shrinkage do not apply."
  )
  keep <- rowSums(expression_matrix >= parameters$low_count_threshold) >= parameters$minimum_samples
  if (!any(keep)) abort("No features remain after low-count filtering.")
  filtered_counts <- expression_matrix[keep, , drop = FALSE]
  features_filtered <- sum(!keep)

  dge <- DGEList(counts = filtered_counts)
  dge <- calcNormFactors(dge, method = "TMM")
  dge <- estimateDisp(dge, design_matrix, robust = TRUE)
  fit <- glmQLFit(dge, design_matrix, robust = TRUE)
  qlf <- glmQLFTest(fit, contrast = contrast_weights)
  qlf_table <- topTags(qlf, n = Inf, sort.by = "none")$table
  heatmap_expression <- cpm(dge, log = TRUE, prior.count = 2)
  heatmap_source <- "edgeR TMM-normalized log2 CPM"
  table <- data.frame(
    feature_id = rownames(qlf_table), average_log_cpm = qlf_table$logCPM,
    log2_fold_change = qlf_table$logFC,
    standard_error = rep(NA_real_, nrow(qlf_table)),
    statistic = qlf_table$F, p_value = qlf_table$PValue,
    adjusted_p_value = p.adjust(qlf_table$PValue, method = "BH"),
    stringsAsFactors = FALSE, check.names = FALSE
  )
  abundance <- table$average_log_cpm
  ma_x <- abundance
  ma_x_label <- "average log2 CPM"
} else if (identical(request$method, "limma_voom")) {
  runner_warnings <- c(
    runner_warnings,
    "limma-voom uses the configured explicit low-count filter, TMM normalization, and precision weights; DESeq2 independent filtering and fold-change shrinkage do not apply."
  )
  keep <- rowSums(expression_matrix >= parameters$low_count_threshold) >= parameters$minimum_samples
  if (!any(keep)) abort("No features remain after low-count filtering.")
  filtered_counts <- expression_matrix[keep, , drop = FALSE]
  features_filtered <- sum(!keep)

  dge <- DGEList(counts = filtered_counts)
  dge <- calcNormFactors(dge, method = "TMM")
  voom_fit <- voom(dge, design_matrix, plot = FALSE)
  fit <- lmFit(voom_fit, design_matrix)
  contrast_matrix <- matrix(
    contrast_weights, ncol = 1L,
    dimnames = list(colnames(design_matrix), paste(contrast$numerator, "minus", contrast$denominator))
  )
  fit <- eBayes(contrasts.fit(fit, contrast_matrix))
  heatmap_expression <- voom_fit$E
  heatmap_source <- "limma-voom TMM-normalized log2 CPM"
  table <- data.frame(
    feature_id = rownames(voom_fit$E), average_log_cpm = fit$Amean,
    log2_fold_change = fit$coefficients[, 1L],
    standard_error = fit$stdev.unscaled[, 1L] * fit$sigma,
    statistic = fit$t[, 1L], p_value = fit$p.value[, 1L],
    adjusted_p_value = p.adjust(fit$p.value[, 1L], method = "BH"),
    stringsAsFactors = FALSE, check.names = FALSE
  )
  abundance <- table$average_log_cpm
  ma_x <- abundance
  ma_x_label <- "average log2 CPM"
} else {
  runner_warnings <- c(
    runner_warnings,
    "Count filtering, DESeq2 independent filtering, and fold-change shrinkage do not apply to limma log-expression fits."
  )
  fit <- lmFit(expression_matrix, design_matrix)
  contrast_matrix <- matrix(
    contrast_weights, ncol = 1L,
    dimnames = list(colnames(design_matrix), paste(contrast$numerator, "minus", contrast$denominator))
  )
  fit <- eBayes(contrasts.fit(fit, contrast_matrix), trend = TRUE)
  heatmap_expression <- expression_matrix
  heatmap_source <- "input log-expression assay"
  table <- data.frame(
    feature_id = rownames(expression_matrix), average_expression = fit$Amean,
    log2_fold_change = fit$coefficients[, 1L],
    standard_error = fit$stdev.unscaled[, 1L] * fit$sigma,
    statistic = fit$t[, 1L], p_value = fit$p.value[, 1L],
    adjusted_p_value = p.adjust(fit$p.value[, 1L], method = "BH"),
    stringsAsFactors = FALSE, check.names = FALSE
  )
  abundance <- table$average_expression
  ma_x <- abundance
  ma_x_label <- "average log2 expression"
}

symbol_index <- match(table$feature_id, feature_metadata$feature_id)
table$gene_symbol <- ifelse(is.na(symbol_index), "", feature_metadata$gene_symbol[symbol_index])
table$contrast <- request$contrast_label
table$method <- method_label
table <- table[, c(
  "feature_id", "gene_symbol", setdiff(names(table), c("feature_id", "gene_symbol"))
), drop = FALSE]
table$significant <- !is.na(table$adjusted_p_value) & table$adjusted_p_value <= parameters$fdr_threshold &
  !is.na(table$log2_fold_change) & abs(table$log2_fold_change) >= parameters$absolute_log2_fold_change
ordering <- order(is.na(table$adjusted_p_value), table$adjusted_p_value, -abs(table$log2_fold_change), table$feature_id, na.last = TRUE)
table <- table[ordering, , drop = FALSE]
ma_x <- ma_x[ordering]
write.table(table, file.path(output_dir, "differential_expression.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "")
write.table(table[table$significant, , drop = FALSE], file.path(output_dir, "significant_results.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "")
expression_output <- data.frame(
  feature_id = table$feature_id,
  heatmap_expression[table$feature_id, , drop = FALSE],
  check.names = FALSE
)
write.table(
  expression_output, file.path(output_dir, "normalized_expression.tsv"),
  sep = "\t", row.names = FALSE, quote = FALSE, na = ""
)
design_output <- data.frame(sample_id = rownames(design_matrix), design_matrix, check.names = FALSE)
write.table(design_output, file.path(output_dir, "design_matrix.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)

contrast_document <- list(
  schema_version = "1.0.0", variable = contrast$variable, numerator = contrast$numerator,
  denominator = contrast$denominator, label = request$contrast_label,
  coefficient_definition = paste(contrast$numerator, "minus", contrast$denominator)
)
if (!identical(request$method, "deseq2")) {
  contrast_document$design_coefficient_weights <- as.list(contrast_weights)
}
write_json(contrast_document, file.path(output_dir, "contrast.json"))

finite_p <- pmax(table$p_value, .Machine$double.xmin, na.rm = FALSE)
p_values <- table$p_value[is.finite(table$p_value)]
p_value_breaks <- seq(0, 1, length.out = 21L)
p_value_histogram <- if (length(p_values)) {
  hist(p_values, breaks = p_value_breaks, plot = FALSE, include.lowest = TRUE, right = FALSE)
} else {
  list(counts = integer(length(p_value_breaks) - 1L))
}
p_value_bins <- lapply(seq_along(p_value_histogram$counts), function(index) list(
  start = p_value_breaks[[index]], end = p_value_breaks[[index + 1L]],
  count = unname(p_value_histogram$counts[[index]])
))
write_json(
  list(
    schema_version = "1.0.0", analysis_id = request$analysis_id,
    bin_width = 0.05, finite_p_value_count = length(p_values),
    missing_p_value_count = sum(!is.finite(table$p_value)), bins = p_value_bins
  ),
  file.path(output_dir, "p_value_distribution.json")
)

top_feature_count <- min(30L, nrow(table))
top_feature_ids <- table$feature_id[seq_len(top_feature_count)]
heatmap_matrix <- heatmap_expression[top_feature_ids, , drop = FALSE]
feature_means <- rowMeans(heatmap_matrix)
feature_sds <- apply(heatmap_matrix, 1L, sd)
feature_sds[!is.finite(feature_sds) | feature_sds == 0] <- 1
heatmap_z <- sweep(sweep(heatmap_matrix, 1L, feature_means, "-"), 1L, feature_sds, "/")
contrast_rank <- match(
  as.character(metadata[[contrast$variable]]), c(contrast$denominator, contrast$numerator)
)
contrast_rank[is.na(contrast_rank)] <- 3L
if (!is.null(design$block_column)) {
  sample_order <- order(
    as.character(metadata[[design$block_column]]), contrast_rank, metadata$sample_id
  )
  sample_ordering <- paste(design$block_column, "then", contrast$variable)
} else {
  sample_order <- order(contrast_rank, metadata$sample_id)
  sample_ordering <- paste(contrast$variable, "then sample_id")
}
heatmap_z <- heatmap_z[, sample_order, drop = FALSE]
ordered_sample_ids <- colnames(heatmap_z)
heatmap_metadata <- setNames(lapply(sample_order, function(row_index) {
  row <- metadata[row_index, , drop = FALSE]
  as.list(vapply(row, function(value) as.character(value[[1L]]), character(1L)))
}), ordered_sample_ids)
feature_annotations <- setNames(lapply(top_feature_ids, function(feature_id) {
  row <- table[table$feature_id == feature_id, , drop = FALSE]
  list(
    log2_fold_change = row$log2_fold_change[[1L]],
    adjusted_p_value = row$adjusted_p_value[[1L]], significant = row$significant[[1L]]
  )
}), top_feature_ids)
write_json(
  list(
    schema_version = "1.0.0", analysis_id = request$analysis_id, assay = request$assay,
    scale = "feature_z_score", source = heatmap_source, sample_ordering = sample_ordering,
    feature_ids = as.list(top_feature_ids), sample_ids = as.list(ordered_sample_ids),
    values = unname(lapply(seq_len(nrow(heatmap_z)), function(index) {
      as.list(unname(heatmap_z[index, ]))
    })),
    metadata = heatmap_metadata, feature_annotations = feature_annotations,
    contrast = list(
      variable = contrast$variable, numerator = contrast$numerator,
      denominator = contrast$denominator
    )
  ),
  file.path(output_dir, "expression_heatmap.json")
)

volcano_points <- lapply(seq_len(nrow(table)), function(index) list(
  feature_id = table$feature_id[[index]], x = table$log2_fold_change[[index]],
  y = if (is.na(finite_p[[index]])) NA_real_ else -log10(finite_p[[index]]),
  adjusted_p_value = table$adjusted_p_value[[index]], significant = table$significant[[index]]
))
ma_points <- lapply(seq_len(nrow(table)), function(index) list(
  feature_id = table$feature_id[[index]], x = ma_x[[index]],
  y = table$log2_fold_change[[index]], adjusted_p_value = table$adjusted_p_value[[index]],
  significant = table$significant[[index]]
))
write_json(list(schema_version = "1.0.0", analysis_id = request$analysis_id,
                x_label = "log2 fold change", y_label = "-log10 p-value", points = volcano_points),
           file.path(output_dir, "volcano_plot.json"))
write_json(list(schema_version = "1.0.0", analysis_id = request$analysis_id,
                x_label = ma_x_label, y_label = "log2 fold change", points = ma_points),
           file.path(output_dir, "ma_plot.json"))

plot_colors <- ifelse(table$significant, "#be123c", "#94a3b8")
svg(file.path(output_dir, "volcano_plot.svg"), width = 8, height = 6, bg = "white")
plot(table$log2_fold_change, -log10(finite_p), pch = 16, cex = 0.55, col = plot_colors,
     xlab = "log2 fold change", ylab = "-log10 p-value", main = "Volcano plot")
abline(v = c(-parameters$absolute_log2_fold_change, parameters$absolute_log2_fold_change), lty = 2, col = "#475569")
dev.off()

svg(file.path(output_dir, "p_value_distribution.svg"), width = 8, height = 5, bg = "white")
barplot(
  p_value_histogram$counts, names.arg = sprintf("%.2f", p_value_breaks[-length(p_value_breaks)]),
  space = 0, col = "#155e75", border = "white", las = 2, cex.names = 0.65,
  ylim = c(0, max(p_value_histogram$counts, 1)),
  xlab = "P-value bin start", ylab = "Feature count", main = "P-value distribution"
)
dev.off()

heatmap_palette <- colorRampPalette(c("#2563eb", "#f8fafc", "#be123c"))(101L)
heatmap_plot <- heatmap_z
heatmap_plot[heatmap_plot < -3] <- -3
heatmap_plot[heatmap_plot > 3] <- 3
svg(file.path(output_dir, "expression_heatmap.svg"), width = 12, height = 8, bg = "white")
par(mar = c(10, 11, 3, 2))
image(
  x = seq_len(ncol(heatmap_z)), y = seq_len(nrow(heatmap_z)),
  z = t(heatmap_plot[nrow(heatmap_plot):1L, , drop = FALSE]),
  col = heatmap_palette, zlim = c(-3, 3), axes = FALSE,
  xlab = "Samples", ylab = "Top differential features", main = "Top-feature expression heatmap"
)
axis(1, at = seq_len(ncol(heatmap_z)), labels = ordered_sample_ids, las = 2, cex.axis = 0.42)
axis(2, at = seq_len(nrow(heatmap_z)), labels = rev(top_feature_ids), las = 2, cex.axis = 0.55)
box()
dev.off()
svg(file.path(output_dir, "ma_plot.svg"), width = 8, height = 6, bg = "white")
plot(ma_x, table$log2_fold_change, pch = 16, cex = 0.55, col = plot_colors,
     xlab = ma_x_label, ylab = "log2 fold change", main = "MA plot")
abline(h = 0, lty = 2, col = "#475569")
dev.off()

diagnostics <- list(
  schema_version = "1.0.0", method = method_label, assay = request$assay, formula = generated_formula,
  design_rank = design_rank, design_columns = colnames(design_matrix), sample_count = nrow(metadata),
  features_input = features_input, features_tested = nrow(table), features_filtered = features_filtered,
  significant_features = sum(table$significant),
  normalization_method = normalization_method, test_statistic = test_statistic,
  independent_filtering_requested = parameters$independent_filtering,
  independent_filtering_applied = independent_filtering_applied,
  shrinkage_requested = parameters$shrinkage, shrinkage_applied = shrinkage_applied,
  r_version = R.version.string, deseq2_version = as.character(packageVersion("DESeq2")),
  edger_version = as.character(packageVersion("edgeR")),
  limma_version = as.character(packageVersion("limma")),
  jsonlite_version = as.character(packageVersion("jsonlite")),
  warnings = as.list(runner_warnings)
)
write_json(diagnostics, file.path(output_dir, "method_diagnostics.json"))
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))

summary_metrics <- list(
  list(label = "Samples", value = nrow(metadata)), list(label = "Features tested", value = nrow(table)),
  list(label = "Significant features", value = sum(table$significant)),
  list(label = "FDR threshold", value = parameters$fdr_threshold)
)
downloads <- list(
  list(type = "table", title = "Complete differential-expression results", path = "differential_expression.tsv"),
  list(type = "table", title = "Significant results", path = "significant_results.tsv"),
  list(type = "table", title = "Normalized expression profiles", path = "normalized_expression.tsv"),
  list(type = "table", title = "Design matrix", path = "design_matrix.tsv"),
  list(type = "file", title = "Method diagnostics", path = "method_diagnostics.json")
)
manifest <- list(
  schema_version = "1.0.0", analysis_type = "differential_expression",
  title = paste0(method_label, ": ", request$contrast_label), summary_metrics = summary_metrics,
  sections = list(
    list(id = "effect_plots", title = "Effect plots", items = list(
      list(type = "plotly_json", title = "Volcano plot", path = "volcano_plot.json"),
      list(type = "plotly_json", title = "MA plot", path = "ma_plot.json"),
      list(type = "plotly_json", title = "P-value distribution", path = "p_value_distribution.json"),
      list(type = "plotly_json", title = "Top-feature expression heatmap", path = "expression_heatmap.json")
    )),
    list(id = "results", title = "Results", items = downloads)
  ), downloads = downloads, warnings = as.list(runner_warnings)
)
write_json(manifest, file.path(output_dir, "result_manifest.json"))

report <- c(
  "---", "title: \"TranscriptForge differential expression\"", "format:", "  html:", "    embed-resources: true", "---", "",
  "## Analysis", "", paste(paste("- Method:", method_label), paste("- Assay:", request$assay),
                           "- Design:", paste0("`", generated_formula, "`"),
                           "- Contrast:", request$contrast_label, "- Samples:", nrow(metadata),
                           "- Features tested:", nrow(table), "- Significant features:", sum(table$significant), sep = "\n"), "",
  "## Volcano plot", "", "![](volcano_plot.svg)", "", "## MA plot", "", "![](ma_plot.svg)", "",
  "## P-value distribution", "", "![](p_value_distribution.svg)", "",
  "## Top-feature expression heatmap", "", "![](expression_heatmap.svg)", "",
  "## Gene-level exploration", "",
  "The normalized expression profile table supports the interactive per-gene detail view.", "",
  "## Interpretation", "", "Results are for research use only and are not clinically validated. Evaluate effect sizes, uncertainty, sample QC, and study design together."
)
writeLines(report, file.path(output_dir, "report.qmd"))
