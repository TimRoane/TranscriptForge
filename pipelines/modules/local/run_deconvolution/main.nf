process RUN_DECONVOLUTION {
    tag 'cell-population-analysis'
    label 'process_medium'
    container 'transcriptforge/deconvolution:bioc-3.22-enrichment'

    publishDir "${params.outdir}/analysis", mode: 'copy', overwrite: true

    input:
    path analysis_request
    path expression_bundle
    path analysis_r
    path reference_manifest

    output:
    path 'results/*', emit: results

    script:
    """
    Rscript ${analysis_r}/deconvolution.R \
      --request ${analysis_request} \
      --bundle ${expression_bundle} \
      --reference-manifest ${reference_manifest} \
      --output-dir results
    (cd results && quarto render report.qmd --to html --output report.html)
    """
}
