#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

assert_true <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

write_json <- function(value, path) {
  writeLines(toJSON(value, auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 12), path)
}

write_matrix <- function(path, feature_ids, sample_ids, values) {
  output <- data.frame(feature_id = feature_ids, values, check.names = FALSE)
  names(output) <- c("feature_id", sample_ids)
  write.table(output, path, sep = "\t", row.names = FALSE, quote = FALSE)
}

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
assert_true(length(script_argument) == 1L, "Unable to locate the acceptance-test script.")
test_script <- normalizePath(sub("^--file=", "", script_argument[[1L]]))
runner <- normalizePath(file.path(dirname(dirname(test_script)), "differential_expression.R"))

root <- tempfile("transcriptforge-r-acceptance-")
dir.create(root)
on.exit(unlink(root, recursive = TRUE), add = TRUE)
bundle_parent <- file.path(root, "bundle")
bundle_root <- file.path(bundle_parent, "expression_bundle")
dir.create(file.path(bundle_root, "assays"), recursive = TRUE)

set.seed(20260716)
pair_count <- 6L
sample_ids <- sprintf("sample_%02d", seq_len(pair_count * 2L))
subject_ids <- rep(sprintf("donor_%02d", seq_len(pair_count)), each = 2L)
treatments <- rep(c("vehicle", "stimulated"), pair_count)
metadata <- data.frame(
  sample_id = sample_ids,
  subject_id = subject_ids,
  treatment = treatments,
  stringsAsFactors = FALSE
)
write.table(
  metadata, file.path(bundle_root, "sample_metadata.tsv"),
  sep = "\t", row.names = FALSE, quote = FALSE
)

up_ids <- sprintf("gene_up_%02d", seq_len(15L))
down_ids <- sprintf("gene_down_%02d", seq_len(15L))
null_ids <- sprintf("gene_null_%02d", seq_len(60L))
low_ids <- sprintf("gene_low_%02d", seq_len(10L))
feature_ids <- c(up_ids, down_ids, null_ids, low_ids)
gene_symbols <- c(
  sprintf("UP%03d", seq_along(up_ids)),
  sprintf("DOWN%03d", seq_along(down_ids)),
  sprintf("NULL%03d", seq_along(null_ids)),
  sprintf("LOW%03d", seq_along(low_ids))
)
feature_metadata <- data.frame(
  feature_id = feature_ids,
  gene_symbol = gene_symbols,
  stringsAsFactors = FALSE
)
write.table(
  feature_metadata, file.path(bundle_root, "feature_metadata.tsv"),
  sep = "\t", row.names = FALSE, quote = FALSE
)

feature_count <- length(feature_ids)
counts <- matrix(0L, nrow = feature_count, ncol = length(sample_ids))
log_expression <- matrix(0, nrow = feature_count, ncol = length(sample_ids))
baseline_counts <- exp(runif(feature_count, log(70), log(260)))
baseline_expression <- runif(feature_count, 5.5, 9.5)
subject_count_effect <- rnorm(pair_count, 0, 0.16)
subject_expression_effect <- rnorm(pair_count, 0, 0.22)
for (feature_index in seq_len(feature_count)) {
  category_effect <- if (feature_index <= 15L) 2 else if (feature_index <= 30L) -2 else 0
  for (sample_index in seq_along(sample_ids)) {
    subject_index <- ceiling(sample_index / 2)
    stimulated <- treatments[[sample_index]] == "stimulated"
    if (feature_index > 90L) {
      counts[feature_index, sample_index] <- rpois(1L, lambda = 1.2)
    } else {
      log2_effect <- if (stimulated) category_effect else 0
      mean_count <- baseline_counts[[feature_index]] *
        exp(subject_count_effect[[subject_index]]) * 2^log2_effect
      counts[feature_index, sample_index] <- rnbinom(1L, mu = mean_count, size = 12)
    }
    log_expression[feature_index, sample_index] <-
      baseline_expression[[feature_index]] +
      subject_expression_effect[[subject_index]] +
      (if (stimulated) category_effect else 0) +
      rnorm(1L, 0, 0.12)
  }
}
write_matrix(
  file.path(bundle_root, "assays", "raw_counts.tsv"),
  feature_ids, sample_ids, counts
)
write_matrix(
  file.path(bundle_root, "assays", "log_expression.tsv"),
  feature_ids, sample_ids, log_expression
)
write_json(
  list(
    schema_version = "1.0.0",
    sample_metadata = "sample_metadata.tsv",
    feature_metadata = "feature_metadata.tsv",
    assays = list(
      list(name = "raw_counts", path = "assays/raw_counts.tsv"),
      list(name = "log_expression", path = "assays/log_expression.tsv")
    )
  ),
  file.path(bundle_root, "bundle_manifest.json")
)

bundle_tar <- file.path(root, "expression_bundle.tar.gz")
old_working_directory <- getwd()
setwd(bundle_parent)
utils::tar(bundle_tar, files = "expression_bundle", compression = "gzip", tar = "internal")
setwd(old_working_directory)

model_metadata <- metadata
model_metadata$subject_id <- factor(model_metadata$subject_id)
model_metadata$treatment <- relevel(factor(model_metadata$treatment), ref = "vehicle")
model_columns <- colnames(model.matrix(~ subject_id + treatment, model_metadata))
model_rank <- qr(model.matrix(~ subject_id + treatment, model_metadata))$rank

request_document <- function(method, assay, formula = "~ subject_id + treatment", rank = model_rank) {
  list(
    schema_version = "1.0.0",
    analysis_id = paste0("acceptance-", method),
    analysis_type = "differential_expression",
    method = method,
    assay = assay,
    random_seed = 20260716,
    design_formula = formula,
    contrast_label = "stimulated versus vehicle within treatment",
    parameters = list(
      design = list(
        primary_variable = "treatment",
        covariates = list(),
        block_column = "subject_id",
        interaction_terms = list(),
        reference_levels = list(treatment = "vehicle")
      ),
      contrast = list(
        variable = "treatment", numerator = "stimulated", denominator = "vehicle"
      ),
      low_count_threshold = 10,
      minimum_samples = 2,
      fdr_threshold = 0.05,
      absolute_log2_fold_change = 1,
      independent_filtering = identical(method, "deseq2"),
      shrinkage = FALSE
    ),
    design_validation = list(
      sample_count = nrow(metadata),
      design_matrix_rank = rank,
      design_matrix_columns = as.list(model_columns),
      warnings = list()
    )
  )
}

run_runner <- function(name, request, should_succeed = TRUE) {
  request_path <- file.path(root, paste0(name, "-request.json"))
  output_dir <- file.path(root, paste0(name, "-results"))
  log_path <- file.path(root, paste0(name, ".log"))
  write_json(request, request_path)
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
  if (should_succeed) {
    assert_true(status == 0L, paste("Runner case failed:", name, log_text))
    assert_true(
      file.exists(file.path(output_dir, "result_manifest.json")),
      paste("Runner case did not publish a Result Manifest:", name)
    )
  } else {
    assert_true(status != 0L, paste("Runner case unexpectedly succeeded:", name))
    assert_true(
      !file.exists(file.path(output_dir, "result_manifest.json")),
      paste("Failed runner case published a Result Manifest:", name)
    )
  }
  list(output_dir = output_dir, log = log_text)
}

formula_failure <- run_runner(
  "formula-disagreement",
  request_document("limma", "log_expression", formula = "~ treatment"),
  should_succeed = FALSE
)
assert_true(
  grepl("formula disagrees with frozen server preview", formula_failure$log, fixed = TRUE),
  "Formula disagreement did not produce the expected actionable error."
)
cat("PASS formula disagreement is rejected before fitting\n")

rank_failure <- run_runner(
  "rank-disagreement",
  request_document("limma", "log_expression", rank = 1L),
  should_succeed = FALSE
)
assert_true(
  grepl("R-side design disagrees with server preview", rank_failure$log, fixed = TRUE),
  "Rank disagreement did not produce the expected actionable error."
)
cat("PASS design-rank disagreement is rejected before fitting\n")

check_success <- function(method, output_dir, expected_tested, expected_filtered, recovery_minimum) {
  table <- read.delim(
    file.path(output_dir, "differential_expression.tsv"),
    check.names = FALSE, stringsAsFactors = FALSE
  )
  diagnostics <- fromJSON(file.path(output_dir, "method_diagnostics.json"))
  contrast <- fromJSON(file.path(output_dir, "contrast.json"))
  profiles <- read.delim(
    file.path(output_dir, "normalized_expression.tsv"),
    check.names = FALSE, stringsAsFactors = FALSE
  )
  assert_true(nrow(table) == expected_tested, paste(method, "tested-feature count is wrong."))
  assert_true(
    diagnostics$features_filtered == expected_filtered,
    paste(method, "filtered-feature diagnostic is wrong.")
  )
  assert_true(
    nrow(profiles) == expected_tested && ncol(profiles) == length(sample_ids) + 1L,
    paste(method, "normalized-expression profile dimensions are wrong.")
  )
  assert_true(
    identical(contrast$coefficient_definition, "stimulated minus vehicle"),
    paste(method, "contrast direction is not explicit.")
  )
  assert_true(identical(diagnostics$method, method), paste(method, "diagnostic label is wrong."))
  if (method %in% c("edgeR QL", "limma-voom")) {
    assert_true(
      "average_log_cpm" %in% names(table),
      paste(method, "did not publish count-scale abundance semantics.")
    )
    assert_true(
      identical(diagnostics$normalization_method, "edgeR TMM normalization"),
      paste(method, "did not record TMM normalization.")
    )
    assert_true(
      length(contrast$design_coefficient_weights) == length(model_columns),
      paste(method, "did not record the fitted contrast weights.")
    )
  }
  up <- table[table$feature_id %in% up_ids, , drop = FALSE]
  down <- table[table$feature_id %in% down_ids, , drop = FALSE]
  null <- table[table$feature_id %in% null_ids, , drop = FALSE]
  assert_true(median(up$log2_fold_change) > 1.5, paste(method, "lost the positive direction."))
  assert_true(median(down$log2_fold_change) < -1.5, paste(method, "lost the negative direction."))
  assert_true(
    sum(up$significant) >= recovery_minimum,
    paste(method, "did not recover enough known positive effects.")
  )
  assert_true(
    sum(down$significant) >= recovery_minimum,
    paste(method, "did not recover enough known negative effects.")
  )
  assert_true(sum(null$significant) <= 3L, paste(method, "called too many null features."))
  assert_true(
    table$gene_symbol[match(up_ids[[1L]], table$feature_id)] == "UP001",
    paste(method, "did not preserve the feature annotation join.")
  )
  cat(sprintf(
    "PASS %s: tested=%d filtered=%d recovered=%d/%d up and %d/%d down; null calls=%d\n",
    method, nrow(table), expected_filtered, sum(up$significant), length(up_ids),
    sum(down$significant), length(down_ids), sum(null$significant)
  ))
}

deseq2 <- run_runner("deseq2", request_document("deseq2", "raw_counts"))
check_success("DESeq2", deseq2$output_dir, 90L, 10L, 12L)
assert_true(
  !any(read.delim(file.path(deseq2$output_dir, "differential_expression.tsv"))$feature_id %in% low_ids),
  "DESeq2 retained a fixture feature that should have failed low-count filtering."
)
cat("PASS DESeq2 low-count filtering excludes all ten fixture rows\n")

limma <- run_runner("limma", request_document("limma", "log_expression"))
check_success("limma", limma$output_dir, 100L, 0L, 14L)

edger <- run_runner("edger-ql", request_document("edger_ql", "raw_counts"))
check_success("edgeR QL", edger$output_dir, 90L, 10L, 12L)
assert_true(
  !any(read.delim(file.path(edger$output_dir, "differential_expression.tsv"))$feature_id %in% low_ids),
  "edgeR QL retained a fixture feature that should have failed low-count filtering."
)

voom <- run_runner("limma-voom", request_document("limma_voom", "raw_counts"))
check_success("limma-voom", voom$output_dir, 90L, 10L, 12L)
assert_true(
  !any(read.delim(file.path(voom$output_dir, "differential_expression.tsv"))$feature_id %in% low_ids),
  "limma-voom retained a fixture feature that should have failed low-count filtering."
)

cat("All differential-expression R acceptance checks passed.\n")
