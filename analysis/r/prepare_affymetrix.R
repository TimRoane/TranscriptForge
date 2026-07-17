#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

parse_args <- function(args) {
  if (length(args) %% 2 != 0) stop("Arguments must be supplied as --name value pairs.")
  values <- list()
  for (index in seq(1, length(args), by = 2)) {
    key <- sub("^--", "", args[[index]])
    values[[gsub("-", "_", key)]] <- args[[index + 1]]
  }
  values
}

require_value <- function(values, name) {
  value <- values[[name]]
  if (is.null(value) || !nzchar(value)) stop(sprintf("Missing required argument --%s.", name))
  value
}

write_matrix <- function(matrix, path, feature_column = "feature_id") {
  output <- data.frame(matrix, check.names = FALSE, stringsAsFactors = FALSE)
  output <- cbind(setNames(data.frame(rownames(matrix), check.names = FALSE), feature_column), output)
  write.table(output, path, sep = "\t", quote = FALSE, row.names = FALSE, na = "")
}

safe_svg <- function(path, plot_title, draw) {
  svg(path, width = 9, height = 6, onefile = TRUE)
  on.exit(dev.off(), add = TRUE)
  tryCatch(draw(), error = function(error) {
    plot.new()
    graphics::title(main = plot_title)
    text(0.5, 0.5, paste("Plot unavailable:", conditionMessage(error)))
  })
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
manifest_path <- require_value(args, "ingestion_manifest")
cel_dir <- require_value(args, "cel_dir")
output_dir <- require_value(args, "output_dir")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(output_dir, "plots"), recursive = TRUE, showWarnings = FALSE)

manifest <- fromJSON(manifest_path, simplifyVector = FALSE)
normalization <- manifest$platform$normalization
annotation <- manifest$platform$annotation
required_packages <- c(
  "oligo", "oligoClasses", "Biobase", "AnnotationDbi", "DBI",
  normalization$pd_info_package, annotation$package
)
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages)) {
  stop(sprintf("Microarray runtime is missing required packages: %s.", paste(missing_packages, collapse = ", ")))
}
suppressPackageStartupMessages(library(normalization$pd_info_package, character.only = TRUE))
suppressPackageStartupMessages(library(annotation$package, character.only = TRUE))

sample_ids <- vapply(manifest$samples, function(sample) sample$sample_id, character(1))
cel_names <- vapply(manifest$samples, function(sample) sample$cel_file$original_name, character(1))
cel_paths <- file.path(cel_dir, cel_names)
missing_files <- cel_names[!file.exists(cel_paths)]
if (length(missing_files)) stop(sprintf("Staged CEL files are missing: %s.", paste(missing_files, collapse = ", ")))

pheno <- Biobase::AnnotatedDataFrame(data.frame(row.names = sample_ids))
raw_data <- oligo::read.celfiles(cel_paths, phenoData = pheno, verbose = FALSE)
Biobase::sampleNames(raw_data) <- sample_ids
detected_pd_package <- Biobase::annotation(raw_data)
if (!identical(detected_pd_package, normalization$pd_info_package)) {
  stop(sprintf(
    "CEL platform mismatch: oligo selected '%s' but the frozen adapter requires '%s'.",
    detected_pd_package,
    normalization$pd_info_package
  ))
}

probe_eset <- oligo::rma(raw_data, target = normalization$target)
probe_expression <- Biobase::exprs(probe_eset)
feature_data <- Biobase::fData(probe_eset)
cluster_column <- intersect(
  c("transcript_cluster_id", "transcriptclusterid", "transcript_cluster"),
  colnames(feature_data)
)
if (length(cluster_column)) {
  probe_to_cluster <- data.frame(
    probe_id = rownames(probe_expression),
    transcript_cluster_id = as.character(feature_data[[cluster_column[[1]]]]),
    stringsAsFactors = FALSE
  )
} else {
  platform_design <- getExportedValue(normalization$pd_info_package, normalization$pd_info_package)
  platform_connection <- oligoClasses::db(platform_design)
  design_mapping <- DBI::dbGetQuery(
    platform_connection,
    "SELECT fsetid AS probe_id, transcript_cluster_id FROM featureSet"
  )
  design_mapping$probe_id <- as.character(design_mapping$probe_id)
  design_mapping$transcript_cluster_id <- as.character(design_mapping$transcript_cluster_id)
  probe_to_cluster <- merge(
    data.frame(probe_id = rownames(probe_expression), stringsAsFactors = FALSE),
    design_mapping,
    by = "probe_id",
    all.x = TRUE,
    sort = FALSE
  )
}
transcript_clusters <- probe_to_cluster$transcript_cluster_id

annotation_db <- getExportedValue(annotation$package, annotation$package)
cluster_keys <- sort(unique(transcript_clusters[!is.na(transcript_clusters) & nzchar(transcript_clusters)]))
annotation_rows <- AnnotationDbi::select(
  annotation_db,
  keys = cluster_keys,
  keytype = annotation$probe_key,
  columns = unique(c(
    annotation$probe_key,
    annotation$gene_id_field,
    annotation$gene_symbol_field,
    "ENTREZID",
    "GENENAME"
  ))
)
colnames(annotation_rows)[colnames(annotation_rows) == annotation$probe_key] <- "transcript_cluster_id"
colnames(annotation_rows)[colnames(annotation_rows) == annotation$gene_id_field] <- "ensembl_gene_id"
colnames(annotation_rows)[colnames(annotation_rows) == annotation$gene_symbol_field] <- "gene_symbol"
colnames(annotation_rows)[colnames(annotation_rows) == "ENTREZID"] <- "entrez_id"
colnames(annotation_rows)[colnames(annotation_rows) == "GENENAME"] <- "gene_name"
mapping <- merge(
  probe_to_cluster,
  annotation_rows,
  by = "transcript_cluster_id",
  all.x = TRUE,
  sort = FALSE
)
mapping$mapping_status <- ifelse(
  is.na(mapping$ensembl_gene_id) | !nzchar(mapping$ensembl_gene_id),
  "unmapped",
  "mapped"
)
mapping <- mapping[order(mapping$probe_id, mapping$ensembl_gene_id, na.last = TRUE), , drop = FALSE]
write.table(
  mapping,
  file.path(output_dir, "probe_mapping.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE,
  na = ""
)

mapped <- mapping[mapping$mapping_status == "mapped", , drop = FALSE]
if (!nrow(mapped)) stop("The selected annotation package did not map any probes to Ensembl genes.")
mapped$probe_index <- match(mapped$probe_id, rownames(probe_expression))
mapped <- mapped[!is.na(mapped$probe_index), , drop = FALSE]
groups <- split(seq_len(nrow(mapped)), mapped$ensembl_gene_id)
aggregation_method <- manifest$aggregation_method

aggregate_gene <- function(indices) {
  probe_indices <- sort(unique(mapped$probe_index[indices]))
  values <- probe_expression[probe_indices, , drop = FALSE]
  if (aggregation_method == "highest_mad") {
    variability <- apply(values, 1, mad, constant = 1)
    selected <- order(-variability, rownames(values))[[1]]
    as.numeric(values[selected, ])
  } else if (aggregation_method == "median") {
    apply(values, 2, median)
  } else if (aggregation_method == "mean") {
    colMeans(values)
  } else {
    stop(sprintf("Unsupported frozen aggregation method '%s'.", aggregation_method))
  }
}

gene_expression <- do.call(rbind, lapply(groups, aggregate_gene))
rownames(gene_expression) <- names(groups)
colnames(gene_expression) <- sample_ids
gene_expression <- gene_expression[order(rownames(gene_expression)), , drop = FALSE]

gene_metadata <- do.call(rbind, lapply(names(groups), function(gene_id) {
  rows <- mapped[groups[[gene_id]], , drop = FALSE]
  probe_ids <- sort(unique(rows$probe_id))
  selected_probe <- ""
  if (aggregation_method == "highest_mad") {
    probe_indices <- match(probe_ids, rownames(probe_expression))
    values <- probe_expression[probe_indices, , drop = FALSE]
    selected_probe <- probe_ids[order(-apply(values, 1, mad, constant = 1), probe_ids)[[1]]]
  }
  first_value <- function(column) {
    values <- sort(unique(as.character(rows[[column]])))
    values <- values[!is.na(values) & nzchar(values)]
    if (length(values)) values[[1]] else ""
  }
  data.frame(
    feature_id = gene_id,
    ensembl_gene_id = gene_id,
    gene_symbol = first_value("gene_symbol"),
    entrez_id = first_value("entrez_id"),
    gene_name = first_value("gene_name"),
    gene_biotype = "",
    chromosome = "",
    start = "",
    end = "",
    mapping_status = "mapped",
    original_feature_id = paste(probe_ids, collapse = ";"),
    selected_probe_id = selected_probe,
    aggregation_method = aggregation_method,
    stringsAsFactors = FALSE
  )
}))

write_matrix(probe_expression, file.path(output_dir, "probe_expression.tsv"), "probe_id")
write_matrix(gene_expression, file.path(output_dir, "gene_expression.tsv"))
write.table(
  gene_metadata,
  file.path(output_dir, "gene_feature_metadata.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE,
  na = ""
)

raw_intensity <- log2(Biobase::exprs(raw_data) + 1)
raw_median <- apply(raw_intensity, 2, median)
raw_iqr <- apply(raw_intensity, 2, IQR)
normalized_median <- apply(probe_expression, 2, median)
normalized_iqr <- apply(probe_expression, 2, IQR)
robust_z <- function(values) {
  denominator <- mad(values, constant = 1.4826)
  if (!is.finite(denominator) || denominator == 0) return(rep(0, length(values)))
  (values - median(values)) / denominator
}
review <- abs(robust_z(raw_median)) > 3 | abs(robust_z(raw_iqr)) > 3
qc_metrics <- data.frame(
  sample_id = sample_ids,
  raw_log2_median = as.numeric(raw_median),
  raw_log2_iqr = as.numeric(raw_iqr),
  normalized_log2_median = as.numeric(normalized_median),
  normalized_log2_iqr = as.numeric(normalized_iqr),
  status = ifelse(review, "REVIEW", "PASS"),
  reasons = ifelse(review, "INTENSITY_DISTRIBUTION_OUTLIER", ""),
  stringsAsFactors = FALSE
)
write.table(qc_metrics, file.path(output_dir, "array_qc_metrics.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write.table(
  qc_metrics[, c("sample_id", "status", "reasons")],
  file.path(output_dir, "sample_flags.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)

safe_svg(file.path(output_dir, "plots", "raw_intensity_boxplot.svg"), "Raw intensity distributions", function() {
  boxplot(as.data.frame(raw_intensity), las = 2, main = "Raw log2 intensity distributions", ylab = "log2 intensity")
})
safe_svg(file.path(output_dir, "plots", "normalized_expression_boxplot.svg"), "Normalized expression distributions", function() {
  boxplot(as.data.frame(probe_expression), las = 2, main = "RMA normalized probe-set expression", ylab = "log2 expression")
})
safe_svg(file.path(output_dir, "plots", "sample_correlation.svg"), "Sample correlation", function() {
  correlation <- cor(gene_expression, method = "pearson")
  heatmap(correlation, symm = TRUE, margins = c(8, 8), main = "Gene-expression sample correlation")
})
safe_svg(file.path(output_dir, "plots", "pca.svg"), "Microarray PCA", function() {
  if (length(sample_ids) < 2) stop("PCA requires at least two arrays")
  pca <- prcomp(t(gene_expression), center = TRUE, scale. = TRUE, rank. = 2)
  plot(pca$x[, 1], pca$x[, 2], pch = 19, xlab = "PC1", ylab = "PC2", main = "RMA gene-expression PCA")
  text(pca$x[, 1], pca$x[, 2], labels = sample_ids, pos = 3, cex = 0.75)
})

qc_status <- if (any(review)) "REVIEW" else "PASS"
write_json(
  list(
    schema_version = "1.0.0",
    status = qc_status,
    sample_count = length(sample_ids),
    probe_count = nrow(probe_expression),
    gene_count = nrow(gene_expression),
    reviewed_sample_count = sum(review),
    plots = c(
      "plots/raw_intensity_boxplot.svg",
      "plots/normalized_expression_boxplot.svg",
      "plots/sample_correlation.svg",
      "plots/pca.svg"
    )
  ),
  file.path(output_dir, "array_qc_summary.json"),
  pretty = TRUE,
  auto_unbox = TRUE
)
write_json(
  list(
    platform_id = manifest$platform$platform_id,
    platform_definition_sha256 = manifest$platform$definition_sha256,
    adapter_version = manifest$platform$adapter_version,
    rma_target = normalization$target,
    aggregation_method = aggregation_method,
    annotation_confidence = annotation$confidence
  ),
  file.path(output_dir, "parameters.json"),
  pretty = TRUE,
  auto_unbox = TRUE
)

package_versions <- vapply(required_packages, function(package) {
  as.character(utils::packageVersion(package))
}, character(1))
writeLines(
  c(
    sprintf("r: '%s'", getRversion()),
    sprintf("bioconductor: '%s'", as.character(BiocManager::version())),
    "packages:",
    sprintf("  %s: '%s'", names(package_versions), package_versions)
  ),
  file.path(output_dir, "software_versions.yml")
)
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))
