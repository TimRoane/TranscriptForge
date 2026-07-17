# Deterministic gene-set enrichment helpers for differential-expression results.

sha256_file <- function(path) {
  output <- system2("sha256sum", path, stdout = TRUE, stderr = TRUE)
  if (!length(output) || !grepl("^[a-f0-9]{64}\\s", output[[1L]])) {
    abort(paste("Unable to calculate SHA-256 for", basename(path)))
  }
  strsplit(output[[1L]], "\\s+")[[1L]][[1L]]
}

load_gene_set_collection <- function(script_root, collection_id) {
  if (!grepl("^[a-z][a-z0-9_]*$", collection_id)) abort("Gene-set collection ID is unsafe.")
  collection_root <- file.path(script_root, "gene_sets")
  metadata_path <- file.path(collection_root, paste0(collection_id, ".json"))
  if (!file.exists(metadata_path)) abort(paste("Unknown gene-set collection:", collection_id))
  metadata <- fromJSON(metadata_path, simplifyVector = FALSE)
  required <- c(
    "collection_id", "name", "version", "identifier_namespace", "source", "license",
    "gmt_file", "gmt_sha256", "set_count"
  )
  if (!all(required %in% names(metadata)) || !identical(metadata$collection_id, collection_id)) {
    abort("Gene-set collection metadata is malformed.")
  }
  if (!identical(basename(metadata$gmt_file), metadata$gmt_file)) {
    abort("Gene-set collection metadata contains an unsafe GMT path.")
  }
  gmt_path <- file.path(collection_root, metadata$gmt_file)
  if (!file.exists(gmt_path)) abort("Gene-set collection GMT file is missing.")
  actual_sha256 <- sha256_file(gmt_path)
  if (!identical(actual_sha256, metadata$gmt_sha256)) {
    abort("Gene-set collection checksum does not match its versioned metadata.")
  }
  lines <- readLines(gmt_path, warn = FALSE)
  fields <- strsplit(lines[nzchar(lines)], "\t", fixed = TRUE)
  if (!length(fields) || any(lengths(fields) < 3L)) abort("Gene-set GMT is malformed.")
  sets <- lapply(fields, function(row) list(
    gene_set_id = row[[1L]], gene_set_name = row[[2L]], members = unique(row[-c(1L, 2L)])
  ))
  if (length(sets) != metadata$set_count) abort("Gene-set count disagrees with metadata.")
  list(metadata = metadata, sets = sets, gmt_sha256 = actual_sha256)
}

gsea_score <- function(ranked_ids, ranked_scores, members) {
  hits <- ranked_ids %in% members
  hit_count <- sum(hits)
  if (hit_count == 0L || hit_count == length(ranked_ids)) {
    return(list(score = 0, leading_edge = character()))
  }
  weights <- abs(ranked_scores)
  hit_weight_total <- sum(weights[hits])
  if (!is.finite(hit_weight_total) || hit_weight_total == 0) {
    weights[hits] <- 1
    hit_weight_total <- hit_count
  }
  increments <- ifelse(hits, weights / hit_weight_total, -1 / (length(ranked_ids) - hit_count))
  running <- cumsum(increments)
  maximum_index <- which.max(running)
  minimum_index <- which.min(running)
  if (abs(running[[maximum_index]]) >= abs(running[[minimum_index]])) {
    leading <- ranked_ids[seq_len(maximum_index)]
    score <- running[[maximum_index]]
  } else {
    leading <- ranked_ids[seq.int(minimum_index, length(ranked_ids))]
    score <- running[[minimum_index]]
  }
  list(score = unname(score), leading_edge = unique(leading[leading %in% members]))
}

run_ranked_list_enrichment <- function(table, sets, enrichment, seed, fdr_threshold) {
  usable <- is.finite(table$p_value) & is.finite(table$log2_fold_change)
  feature_ids <- table$feature_id[usable]
  scores <- sign(table$log2_fold_change[usable]) * -log10(
    pmax(table$p_value[usable], .Machine$double.xmin)
  )
  ordering <- order(-scores, feature_ids)
  ranked_ids <- feature_ids[ordering]
  ranked_scores <- scores[ordering]
  eligible <- Filter(function(item) {
    size <- sum(unique(item$members) %in% ranked_ids)
    size >= enrichment$minimum_gene_set_size && size <= enrichment$maximum_gene_set_size
  }, sets)
  set.seed(seed)
  results <- lapply(eligible, function(item) {
    mapped_members <- intersect(unique(item$members), ranked_ids)
    observed <- gsea_score(ranked_ids, ranked_scores, mapped_members)
    null_scores <- replicate(enrichment$permutation_count, {
      gsea_score(sample(ranked_ids, replace = FALSE), ranked_scores, mapped_members)$score
    })
    if (observed$score >= 0) {
      same_direction <- null_scores[null_scores >= 0]
      p_value <- (1 + sum(same_direction >= observed$score)) / (1 + length(same_direction))
      scale <- mean(same_direction)
      direction <- "up"
    } else {
      same_direction <- null_scores[null_scores < 0]
      p_value <- (1 + sum(same_direction <= observed$score)) / (1 + length(same_direction))
      scale <- mean(abs(same_direction))
      direction <- "down"
    }
    normalized <- if (length(same_direction) && is.finite(scale) && scale > 0) {
      observed$score / scale
    } else {
      0
    }
    list(
      gene_set_id = item$gene_set_id, gene_set_name = item$gene_set_name,
      direction = direction, set_size = length(mapped_members),
      overlap_size = length(mapped_members), enrichment_score = observed$score,
      normalized_enrichment_score = unname(normalized), odds_ratio = NA_real_,
      p_value = unname(p_value), adjusted_p_value = 1,
      leading_edge = as.list(observed$leading_edge), significant = FALSE
    )
  })
  adjust_enrichment_results(results, fdr_threshold, "normalized_enrichment_score")
}

run_over_representation <- function(table, sets, enrichment, fdr_threshold) {
  universe <- unique(table$feature_id)
  foreground <- unique(table$feature_id[table$significant])
  eligible <- Filter(function(item) {
    size <- sum(unique(item$members) %in% universe)
    size >= enrichment$minimum_gene_set_size && size <= enrichment$maximum_gene_set_size
  }, sets)
  results <- lapply(eligible, function(item) {
    mapped_members <- intersect(unique(item$members), universe)
    overlap <- intersect(mapped_members, foreground)
    a <- length(overlap)
    b <- length(foreground) - a
    c_value <- length(mapped_members) - a
    d <- length(universe) - a - b - c_value
    odds_ratio <- ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c_value + 0.5))
    p_value <- phyper(
      a - 1L, length(mapped_members), length(universe) - length(mapped_members),
      length(foreground), lower.tail = FALSE
    )
    effects <- table$log2_fold_change[match(overlap, table$feature_id)]
    direction <- if (!length(effects) || !any(is.finite(effects))) {
      "mixed"
    } else if (mean(effects, na.rm = TRUE) > 0) {
      "up"
    } else if (mean(effects, na.rm = TRUE) < 0) {
      "down"
    } else {
      "mixed"
    }
    list(
      gene_set_id = item$gene_set_id, gene_set_name = item$gene_set_name,
      direction = direction, set_size = length(mapped_members), overlap_size = a,
      enrichment_score = NA_real_, normalized_enrichment_score = NA_real_,
      odds_ratio = unname(odds_ratio), p_value = unname(p_value), adjusted_p_value = 1,
      leading_edge = as.list(sort(overlap)), significant = FALSE
    )
  })
  adjust_enrichment_results(results, fdr_threshold, "odds_ratio")
}

adjust_enrichment_results <- function(results, fdr_threshold, effect_field) {
  if (!length(results)) return(results)
  adjusted <- p.adjust(vapply(results, function(item) item$p_value, numeric(1L)), method = "BH")
  for (index in seq_along(results)) {
    results[[index]]$adjusted_p_value <- unname(adjusted[[index]])
    results[[index]]$significant <- adjusted[[index]] <= fdr_threshold
  }
  effects <- vapply(results, function(item) item[[effect_field]] %||% 0, numeric(1L))
  effects[!is.finite(effects)] <- 0
  ordering <- order(
    adjusted,
    -abs(effects),
    vapply(results, function(item) item$gene_set_id, character(1L))
  )
  results[ordering]
}

`%||%` <- function(left, right) if (is.null(left)) right else left

write_enrichment_table <- function(results, method, path) {
  rows <- lapply(results, function(item) data.frame(
    gene_set_id = item$gene_set_id,
    gene_set_name = item$gene_set_name,
    method = method,
    direction = item$direction,
    set_size = item$set_size,
    overlap_size = item$overlap_size,
    enrichment_score = item$enrichment_score %||% NA_real_,
    normalized_enrichment_score = item$normalized_enrichment_score %||% NA_real_,
    odds_ratio = item$odds_ratio %||% NA_real_,
    p_value = item$p_value,
    adjusted_p_value = item$adjusted_p_value,
    leading_edge = paste(unlist(item$leading_edge), collapse = ";"),
    significant = item$significant,
    stringsAsFactors = FALSE,
    check.names = FALSE
  ))
  output <- if (length(rows)) do.call(rbind, rows) else data.frame(
    gene_set_id = character(), gene_set_name = character(), method = character(),
    direction = character(), set_size = integer(), overlap_size = integer(),
    enrichment_score = numeric(), normalized_enrichment_score = numeric(),
    odds_ratio = numeric(), p_value = numeric(), adjusted_p_value = numeric(),
    leading_edge = character(), significant = logical(), check.names = FALSE
  )
  write.table(output, path, sep = "\t", row.names = FALSE, quote = FALSE, na = "")
}

write_enrichment_plot <- function(ranked, ora, path) {
  candidates <- c(
    lapply(head(ranked, 5L), function(item) list(
      label = paste(item$gene_set_id, "ranked"), value = item$normalized_enrichment_score
    )),
    lapply(head(ora, 5L), function(item) list(
      label = paste(item$gene_set_id, "ORA"),
      value = -log10(max(item$adjusted_p_value, .Machine$double.xmin))
    ))
  )
  svg(path, width = 10, height = 6, bg = "white")
  if (!length(candidates)) {
    plot.new()
    text(0.5, 0.5, "No gene sets passed the configured size and overlap criteria")
  } else {
    values <- vapply(candidates, function(item) item$value, numeric(1L))
    labels <- vapply(candidates, function(item) item$label, character(1L))
    colors <- ifelse(values >= 0, "#155e75", "#be123c")
    par(mar = c(11, 5, 3, 2))
    barplot(values, names.arg = labels, col = colors, las = 2, cex.names = 0.68,
            ylab = "NES or -log10 adjusted p-value", main = "Gene-set enrichment")
    abline(h = 0, col = "#64748b")
  }
  dev.off()
}
