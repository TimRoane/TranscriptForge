process BUILD_MICROARRAY_EXPRESSION_BUNDLE {
    tag 'microarray-expression-bundle'
    label 'process_low'
    container 'python:3.12-slim'
    publishDir "${params.outdir}/preparation", mode: 'copy', overwrite: true

    input:
    path ingestion_manifest
    path rma_output
    path metadata
    path analysis_package

    output:
    path 'prepared/expression_bundle.tar.gz', emit: archive
    path 'prepared/bundle_manifest.json', emit: manifest
    path 'prepared/bundle_summary.json', emit: summary
    path 'prepared/qc_summary.json', emit: qc
    path 'prepared/feature_mapping_summary.json', emit: mapping

    script:
    """
    PYTHONPATH=. python3 -m transcriptforge_analysis.microarray_bundle_cli \
      --ingestion-manifest ${ingestion_manifest} \
      --gene-expression ${rma_output}/gene_expression.tsv \
      --probe-expression ${rma_output}/probe_expression.tsv \
      --gene-feature-metadata ${rma_output}/gene_feature_metadata.tsv \
      --probe-mapping ${rma_output}/probe_mapping.tsv \
      --array-qc-metrics ${rma_output}/array_qc_metrics.tsv \
      --sample-flags ${rma_output}/sample_flags.tsv \
      --array-qc-summary ${rma_output}/array_qc_summary.json \
      --r-output-dir ${rma_output} --metadata ${metadata} \
      --output-dir prepared \
      --prepared-dataset-id ${params.prepared_dataset_id} \
      --prepared-version ${params.prepared_version}
    """
}
