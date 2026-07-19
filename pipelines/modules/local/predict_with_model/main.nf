process RUN_MODEL_PREDICTION {
    tag 'locked-classifier-prediction'
    label 'process_low'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/prediction", mode: 'copy', overwrite: true

    input:
    path model
    path model_manifest
    path expression_bundle
    path analysis_package

    output:
    path 'results/*', emit: results

    script:
    """
    PYTHON_EXECUTABLE='${projectDir}/../.venv/bin/python'
    if [[ ! -x "\${PYTHON_EXECUTABLE}" ]]; then
      PYTHON_EXECUTABLE=python3
    fi
    PYTHONPATH=. "\${PYTHON_EXECUTABLE}" -m transcriptforge_analysis.classifier_prediction_cli \
      --model ${model} \
      --model-manifest ${model_manifest} \
      --bundle ${expression_bundle} \
      --output-dir results
    """
}
