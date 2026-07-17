process SALMON_QUANT {
    tag "$sample_id"
    label 'process_medium'
    container 'combinelab/salmon:1.11.4'

    input:
    tuple val(sample_id), path(read1), path(read2), val(library_type), val(paired)
    path salmon_index

    output:
    tuple val(sample_id), path("${sample_id}"), emit: quant

    script:
    if (paired) {
        """
        salmon quant --index ${salmon_index} --libType ${library_type} \
          --mates1 ${read1} --mates2 ${read2} --threads ${task.cpus} \
          --validateMappings --output ${sample_id}
        """
    } else {
        """
        salmon quant --index ${salmon_index} --libType ${library_type} \
          --unmatedReads ${read1} --threads ${task.cpus} \
          --validateMappings --output ${sample_id}
        """
    }
}
