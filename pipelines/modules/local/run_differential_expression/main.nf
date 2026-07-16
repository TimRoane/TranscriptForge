process RUN_DIFFERENTIAL_EXPRESSION {
    tag 'differential-expression'
    label 'process_high'
    container 'transcriptforge/differential-expression:bioc-3.23'

    publishDir "${params.outdir}/analysis", mode: 'copy', overwrite: true

    input:
    path analysis_request
    path expression_bundle
    path analysis_r

    output:
    path 'results/*', emit: results

    script:
    """
    Rscript ${analysis_r}/differential_expression.R \
      --request ${analysis_request} \
      --bundle ${expression_bundle} \
      --output-dir results
    (cd results && quarto render report.qmd --to html --output report.html)
    """
}
