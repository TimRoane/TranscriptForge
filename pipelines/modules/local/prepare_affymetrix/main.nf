process PREPARE_AFFYMETRIX {
    tag 'affymetrix-rma'
    label 'process_high'
    container 'transcriptforge/microarray:bioc-3.23'
    publishDir "${params.outdir}/microarray/rma", mode: 'copy', overwrite: true

    input:
    path ingestion_manifest
    path cels
    path analysis_r

    output:
    path 'rma', emit: results

    script:
    """
    Rscript ${analysis_r}/prepare_affymetrix.R \
      --ingestion-manifest ${ingestion_manifest} \
      --cel-dir ${cels} \
      --output-dir rma
    """
}
