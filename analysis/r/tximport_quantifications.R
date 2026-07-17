#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(tximport)
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

write_matrix <- function(matrix, target, integer = FALSE) {
  if (integer) matrix <- round(matrix)
  frame <- data.frame(feature_id = rownames(matrix), matrix, check.names = FALSE)
  write.table(frame, target, sep = "\t", row.names = FALSE, quote = FALSE, na = "")
}

safe_percent <- function(numerator, denominator) {
  if (is.na(numerator) || denominator <= 0) return(NA_real_)
  100 * numerator / denominator
}

upper_outlier <- function(values) {
  if (length(values) < 4L || any(!is.finite(values))) return(rep(FALSE, length(values)))
  quartiles <- quantile(values, c(0.25, 0.75), names = FALSE, type = 7)
  threshold <- quartiles[[2L]] + 3 * (quartiles[[2L]] - quartiles[[1L]])
  values > threshold
}

lower_outlier <- function(values) {
  if (length(values) < 4L || any(!is.finite(values))) return(rep(FALSE, length(values)))
  quartiles <- quantile(values, c(0.25, 0.75), names = FALSE, type = 7)
  threshold <- quartiles[[1L]] - 3 * (quartiles[[2L]] - quartiles[[1L]])
  values < threshold
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("execution-manifest", "tx2gene", "quant-root", "output-dir")
missing <- required[!required %in% names(args)]
if (length(missing)) abort(paste("Missing arguments:", paste(missing, collapse = ", ")))

execution <- fromJSON(args$`execution-manifest`, simplifyVector = FALSE)
sample_ids <- vapply(execution$samples, function(item) item$sample_id, character(1L))
if (anyDuplicated(sample_ids)) abort("Execution manifest contains duplicate samples.")
files <- file.path(args$`quant-root`, sample_ids, "quant.sf")
names(files) <- sample_ids
if (any(!file.exists(files))) abort(paste("Missing Salmon quant.sf:", paste(files[!file.exists(files)], collapse = ", ")))

tx2gene <- read.delim(args$tx2gene, check.names = FALSE, stringsAsFactors = FALSE)
required_mapping <- c("transcript_id", "gene_id")
if (!all(required_mapping %in% names(tx2gene))) {
  abort("tx2gene must contain transcript_id and gene_id columns.")
}
if (anyDuplicated(tx2gene$transcript_id)) abort("tx2gene contains duplicate transcript IDs.")

imported <- tximport(
  files,
  type = "salmon",
  tx2gene = tx2gene[, required_mapping],
  ignoreTxVersion = FALSE
)
transcripts <- tximport(files, type = "salmon", txOut = TRUE, ignoreTxVersion = FALSE)
if (!identical(colnames(imported$counts), sample_ids)) abort("tximport changed sample ordering.")
if (!identical(colnames(transcripts$counts), sample_ids)) abort("Transcript import changed sample ordering.")
for (matrix in list(imported$counts, imported$abundance, transcripts$counts, transcripts$abundance)) {
  if (any(!is.finite(matrix)) || any(matrix < 0)) abort("tximport produced invalid abundance values.")
}

dir.create(args$`output-dir`, recursive = TRUE, showWarnings = FALSE)
write_matrix(imported$counts, file.path(args$`output-dir`, "gene_counts.tsv"), integer = TRUE)
write_matrix(imported$abundance, file.path(args$`output-dir`, "gene_tpm.tsv"))
write_matrix(imported$length, file.path(args$`output-dir`, "gene_effective_length.tsv"))
write_matrix(transcripts$counts, file.path(args$`output-dir`, "transcript_counts.tsv"))
write_matrix(transcripts$abundance, file.path(args$`output-dir`, "transcript_tpm.tsv"))
write_matrix(transcripts$length, file.path(args$`output-dir`, "transcript_effective_length.tsv"))

gene_annotation <- tx2gene[!duplicated(tx2gene$gene_id), , drop = FALSE]
gene_annotation <- gene_annotation[match(rownames(imported$counts), gene_annotation$gene_id), , drop = FALSE]
seqnames <- if ("seqname" %in% names(gene_annotation)) gene_annotation$seqname else rep("", nrow(gene_annotation))
gene_types <- if ("gene_type" %in% names(gene_annotation)) gene_annotation$gene_type else rep("", nrow(gene_annotation))
mitochondrial_available <- any(nzchar(seqnames))
ribosomal_available <- any(nzchar(gene_types))
mitochondrial <- toupper(sub("^CHR", "", seqnames, ignore.case = TRUE)) %in% c("M", "MT")
ribosomal <- grepl("(^|_)rrna($|_)", tolower(gene_types))

rounded_counts <- round(imported$counts)
library_sizes <- colSums(rounded_counts)
detected_genes <- colSums(rounded_counts > 0)
mitochondrial_counts <- if (mitochondrial_available) colSums(rounded_counts[mitochondrial, , drop = FALSE]) else rep(NA_real_, length(sample_ids))
ribosomal_counts <- if (ribosomal_available) colSums(rounded_counts[ribosomal, , drop = FALSE]) else rep(NA_real_, length(sample_ids))

mapping <- lapply(sample_ids, function(sample_id) {
  path <- file.path(args$`quant-root`, sample_id, "aux_info", "meta_info.json")
  if (!file.exists(path)) abort(paste("Missing Salmon meta_info.json for", sample_id))
  fromJSON(path, simplifyVector = TRUE)
})
processed_reads <- vapply(mapping, function(item) as.numeric(item$num_processed), numeric(1L))
mapped_reads <- vapply(mapping, function(item) as.numeric(item$num_mapped), numeric(1L))
mapping_rate <- 100 * mapped_reads / pmax(processed_reads, 1)

log_counts <- log1p(rounded_counts)
mean_correlation <- rep(NA_real_, length(sample_ids))
if (length(sample_ids) > 1L && nrow(log_counts) > 1L) {
  correlations <- suppressWarnings(cor(log_counts, method = "pearson"))
  diag(correlations) <- NA_real_
  mean_correlation <- colMeans(correlations, na.rm = TRUE)
}

pca_distance <- rep(NA_real_, length(sample_ids))
if (length(sample_ids) > 2L && sum(apply(log_counts, 1L, var) > 0) > 1L) {
  pca <- prcomp(t(log_counts), center = TRUE, scale. = FALSE)
  component_count <- min(5L, ncol(pca$x), length(sample_ids) - 1L)
  if (component_count > 0L) {
    pca_distance <- rowSums(pca$x[, seq_len(component_count), drop = FALSE]^2)
  }
}

flags <- lapply(seq_along(sample_ids), function(index) character())
mapping_flags <- lower_outlier(mapping_rate)
correlation_flags <- lower_outlier(mean_correlation)
pca_flags <- upper_outlier(pca_distance)
for (index in seq_along(sample_ids)) {
  if (mapping_flags[[index]]) flags[[index]] <- c(flags[[index]], "low_mapping_rate")
  if (correlation_flags[[index]]) flags[[index]] <- c(flags[[index]], "low_sample_correlation")
  if (pca_flags[[index]]) flags[[index]] <- c(flags[[index]], "pca_outlier")
}

qc <- data.frame(
  sample_id = sample_ids,
  lane_count = vapply(execution$samples, function(item) as.integer(item$lane_count), integer(1L)),
  processed_reads = processed_reads,
  mapped_reads = mapped_reads,
  mapping_rate_percent = mapping_rate,
  library_size = library_sizes,
  detected_genes = detected_genes,
  detected_genes_percent = 100 * detected_genes / nrow(rounded_counts),
  mitochondrial_counts = mitochondrial_counts,
  mitochondrial_percent = mapply(safe_percent, mitochondrial_counts, library_sizes),
  ribosomal_counts = ribosomal_counts,
  ribosomal_percent = mapply(safe_percent, ribosomal_counts, library_sizes),
  mean_sample_correlation = mean_correlation,
  pca_squared_distance = pca_distance,
  flags = vapply(flags, function(item) paste(item, collapse = ";"), character(1L)),
  check.names = FALSE
)
write.table(
  qc,
  file.path(args$`output-dir`, "raw_rnaseq_qc_metrics.tsv"),
  sep = "\t",
  row.names = FALSE,
  quote = FALSE,
  na = ""
)

flagged <- vapply(flags, length, integer(1L)) > 0L
qc_summary <- list(
  schema_version = "1.0.0",
  status = if (any(flagged)) "REVIEW" else "PASS",
  sample_count = length(sample_ids),
  flagged_sample_count = sum(flagged),
  mitochondrial_metrics_available = mitochondrial_available,
  ribosomal_metrics_available = ribosomal_available,
  outlier_policy = "Flag only; no samples are automatically excluded. Tukey 3x-IQR fences require at least four samples.",
  sample_flags = setNames(flags, sample_ids)
)
writeLines(
  toJSON(qc_summary, auto_unbox = TRUE, pretty = TRUE),
  file.path(args$`output-dir`, "raw_rnaseq_qc_summary.json")
)

summary <- list(
  schema_version = "1.1.0",
  method = "tximport",
  tximport_version = as.character(packageVersion("tximport")),
  sample_count = length(sample_ids),
  gene_count = nrow(imported$counts),
  transcript_count = nrow(transcripts$counts),
  counts_export = "rounded_estimated_counts",
  transcript_abundance_export = "unrounded_salmon_estimates",
  sample_ids = sample_ids
)
writeLines(toJSON(summary, auto_unbox = TRUE, pretty = TRUE), file.path(args$`output-dir`, "tximport_summary.json"))
