process VERIFY_RAW_INPUTS {
    tag 'verify-frozen-raw-inputs'
    label 'process_low'
    container 'python:3.12-slim'
    publishDir "${params.outdir}/raw-rnaseq/provenance", mode: 'copy', overwrite: true

    input:
    path ingestion_manifest
    path reference_definition
    path reads_dir
    path analysis_package

    output:
    path 'verified/execution_manifest.json', emit: manifest
    path 'verified/sample_metadata.tsv', emit: metadata
    path 'verified/merged_reads', emit: reads

    script:
    """
    PYTHONPATH=. python3 -m transcriptforge_analysis.raw_inputs \
      --ingestion ${ingestion_manifest} --definition ${reference_definition} \
      --reads-dir ${reads_dir} --output-dir verified
    """
}
