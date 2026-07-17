process MULTIQC_RAW_RNASEQ {
    tag 'raw-rnaseq-multiqc'
    label 'process_low'
    container 'ewels/multiqc:1.32'
    publishDir "${params.outdir}/raw-rnaseq/multiqc", mode: 'copy', overwrite: true

    input:
    path qc_inputs

    output:
    path 'multiqc_report.html', emit: report
    path 'multiqc_data.tar.gz', emit: data

    script:
    """
    multiqc --force --filename multiqc_report.html --outdir multiqc-output .
    cp multiqc-output/multiqc_report.html multiqc_report.html
    tar --create --gzip --file multiqc_data.tar.gz -C multiqc-output multiqc_report_data
    """
}
