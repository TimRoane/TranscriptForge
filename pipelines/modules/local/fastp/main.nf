process FASTP_TRIM {
    tag "$sample_id"
    label 'process_medium'
    container 'quay.io/biocontainers/fastp:0.24.0--heae3180_1'
    publishDir "${params.outdir}/raw-rnaseq/fastp", mode: 'copy', overwrite: true,
        pattern: '*.{json,html}'

    input:
    tuple val(sample_id), path(read1), path(read2), val(library_type), val(paired)

    output:
    tuple val(sample_id), path("${sample_id}.trimmed_R1.fastq.gz"),
        path("${sample_id}.trimmed_R2.fastq.gz"), val(library_type), val(paired), emit: reads
    tuple val(sample_id), path("${sample_id}.fastp.json"),
        path("${sample_id}.fastp.html"), emit: reports

    script:
    if (read2) {
        """
        fastp --thread ${task.cpus} --in1 ${read1} --in2 ${read2} \
          --out1 ${sample_id}.trimmed_R1.fastq.gz --out2 ${sample_id}.trimmed_R2.fastq.gz \
          --json ${sample_id}.fastp.json --html ${sample_id}.fastp.html
        """
    } else {
        """
        fastp --thread ${task.cpus} --in1 ${read1} --out1 ${sample_id}.trimmed_R1.fastq.gz \
          --json ${sample_id}.fastp.json --html ${sample_id}.fastp.html
        gzip --no-name </dev/null > ${sample_id}.trimmed_R2.fastq.gz
        """
    }
}
