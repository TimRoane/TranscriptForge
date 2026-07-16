process BUILD_EXPRESSION_BUNDLE {
    tag 'canonical-expression-bundle'
    label 'process_low'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/preparation", mode: 'copy', overwrite: true

    input:
    path validation_config
    path matrix
    path metadata
    path validation_report
    path dataset_manifest
    path analysis_package

    output:
    path 'prepared/expression_bundle.tar.gz', emit: archive
    path 'prepared/bundle_manifest.json', emit: manifest
    path 'prepared/bundle_summary.json', emit: summary
    path 'prepared/qc_summary.json', emit: qc
    path 'prepared/feature_mapping_summary.json', emit: mapping

    script:
    """
    PYTHONPATH=. python3 -m transcriptforge_analysis.bundle_cli \
      --config ${validation_config} \
      --matrix ${matrix} \
      --metadata ${metadata} \
      --output-dir prepared
    """
}
