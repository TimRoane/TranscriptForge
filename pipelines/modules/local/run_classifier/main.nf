process RUN_CLASSIFIER {
    tag 'elastic-net-classifier'
    label 'process_medium'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/analysis", mode: 'copy', overwrite: true

    input:
    path analysis_request
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
    PYTHONPATH=. "\${PYTHON_EXECUTABLE}" -m transcriptforge_analysis.classifier_cli \
      --request ${analysis_request} \
      --bundle ${expression_bundle} \
      --output-dir results
    if command -v quarto >/dev/null 2>&1; then
      (cd results && quarto render report.qmd --to html --output report.html)
    fi
    """
}
