process FASTQC_READS {
    tag "$sample_id"
    label 'process_medium'
    container 'biocontainers/fastqc:v0.12.1_cv1'
    publishDir "${params.outdir}/raw-rnaseq/fastqc", mode: 'copy', overwrite: true

    input:
    tuple val(sample_id), path(read1), path(read2), val(library_type), val(paired)

    output:
    tuple val(sample_id), path("${sample_id}_fastqc"), emit: results

    script:
    def reads = read2 ? "${read1} ${read2}" : "${read1}"
    """
    mkdir ${sample_id}_fastqc
    fastqc --threads ${task.cpus} --outdir ${sample_id}_fastqc ${reads}
    """
}
