process TXIMPORT_GENE_SUMMARIES {
    tag 'tximport-gene-summaries'
    label 'process_low'
    container 'bioconductor/bioconductor_docker:RELEASE_3_20'
    publishDir "${params.outdir}/raw-rnaseq/quantification", mode: 'copy', overwrite: true,
        saveAs: { filename -> filename.tokenize('/')[-1] }

    input:
    path quantifications
    path tx2gene
    path execution_manifest
    path analysis_r

    output:
    path 'tximport/gene_counts.tsv', emit: counts
    path 'tximport/gene_tpm.tsv', emit: tpm
    path 'tximport/gene_effective_length.tsv', emit: lengths
    path 'tximport/transcript_counts.tsv', emit: transcript_counts
    path 'tximport/transcript_tpm.tsv', emit: transcript_tpm
    path 'tximport/transcript_effective_length.tsv', emit: transcript_lengths
    path 'tximport/salmon_quantifications.tar.gz', emit: salmon_quantifications
    path 'tximport/raw_rnaseq_qc_metrics.tsv', emit: qc_metrics
    path 'tximport/raw_rnaseq_qc_summary.json', emit: qc_summary
    path 'tximport/tximport_summary.json', emit: summary

    script:
    """
    Rscript ${analysis_r}/tximport_quantifications.R \
      --execution-manifest ${execution_manifest} --tx2gene ${tx2gene} \
      --quant-root . --output-dir tximport
    tar --create --gzip --file tximport/salmon_quantifications.tar.gz \
      */quant.sf */aux_info/meta_info.json */cmd_info.json */lib_format_counts.json
    """
}
