process VALIDATE_COUNT_MATRIX {
    tag 'count-matrix-validation'
    label 'process_low'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/validation", mode: 'copy', overwrite: true

    input:
    path validation_config
    path matrix
    path metadata
    path analysis_package

    output:
    path 'validation_report.json', emit: report
    path 'dataset_manifest.json', optional: true, emit: manifest

    script:
    """
    PYTHONPATH=. python3 -m transcriptforge_analysis.cli \
      --config ${validation_config} \
      --matrix ${matrix} \
      --metadata ${metadata} \
      --output validation_report.json \
      --manifest-output dataset_manifest.json
    """
}
