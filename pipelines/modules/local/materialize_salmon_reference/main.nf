process MATERIALIZE_SALMON_REFERENCE {
    tag 'materialize-salmon-reference'
    label 'process_high_memory'
    container 'combinelab/salmon:1.11.4'
    publishDir "${params.outdir}/raw-rnaseq/reference", mode: 'copy', overwrite: true,
        pattern: 'materialized_reference/{reference_materialization.json,tx2gene.tsv}',
        saveAs: { filename -> filename.tokenize('/')[-1] }

    input:
    path reference_definition
    path analysis_package
    path reference_assets

    output:
    path 'materialized_reference/reference_materialization.json', emit: manifest
    path 'materialized_reference/tx2gene.tsv', emit: tx2gene
    path 'materialized_reference/salmon_index', emit: index

    script:
    def assetArgument = reference_assets ? "--asset-dir ${reference_assets}" : ''
    def cacheUriArgument = params.reference_cache_uri ? "--cache-uri ${params.reference_cache_uri}" : ''
    """
    PYTHONPATH=. python3 -m transcriptforge_analysis.raw_reference \
      --definition ${reference_definition} --cache-root ${params.reference_cache} \
      --output-dir materialized_reference ${assetArgument} ${cacheUriArgument}
    """
}
