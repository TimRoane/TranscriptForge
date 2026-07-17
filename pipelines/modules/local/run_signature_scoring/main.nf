process RUN_SIGNATURE_SCORING {
    tag 'signature-scoring'
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
    PYTHONPATH=. python3 -m transcriptforge_analysis.signature_scoring_cli \
      --request ${analysis_request} \
      --bundle ${expression_bundle} \
      --output-dir results
    (cd results && quarto render report.qmd --to html --output report.html)
    """
}
