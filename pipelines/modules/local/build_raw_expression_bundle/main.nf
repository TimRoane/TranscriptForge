process BUILD_RAW_EXPRESSION_BUNDLE {
    tag 'raw-rnaseq-expression-bundle'
    label 'process_low'
    container 'python:3.12-slim'
    publishDir "${params.outdir}/preparation", mode: 'copy', overwrite: true

    input:
    path execution_manifest
    path counts
    path tpm
    path transcript_tpm
    path raw_qc_metrics
    path raw_qc_summary
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
    PYTHONPATH=. python3 -m transcriptforge_analysis.raw_bundle_cli \
      --execution-manifest ${execution_manifest} --counts ${counts} --tpm ${tpm} \
      --transcript-tpm ${transcript_tpm} --raw-qc-metrics ${raw_qc_metrics} \
      --raw-qc-summary ${raw_qc_summary} \
      --metadata ${metadata} --output-dir prepared \
      --prepared-dataset-id ${params.prepared_dataset_id} \
      --prepared-version ${params.prepared_version}
    """
}
