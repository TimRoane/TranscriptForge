nextflow.enable.dsl = 2

include { VALIDATE_COUNT_MATRIX } from './modules/local/validate_matrix/main'
include { BUILD_EXPRESSION_BUNDLE } from './modules/local/build_expression_bundle/main'
include { RUN_DIMENSION_REDUCTION } from './modules/local/run_pca/main'
include { RUN_DIFFERENTIAL_EXPRESSION } from './modules/local/run_differential_expression/main'
include { RUN_SIGNATURE_SCORING } from './modules/local/run_signature_scoring/main'
include { RUN_GSVA_SCORING } from './modules/local/run_gsva_scoring/main'
include { VERIFY_RAW_INPUTS } from './modules/local/verify_raw_inputs/main'
include { MATERIALIZE_SALMON_REFERENCE } from './modules/local/materialize_salmon_reference/main'
include { FASTQC_READS } from './modules/local/fastqc/main'
include { FASTP_TRIM } from './modules/local/fastp/main'
include { SALMON_QUANT } from './modules/local/salmon_quant/main'
include { TXIMPORT_GENE_SUMMARIES } from './modules/local/tximport/main'
include { MULTIQC_RAW_RNASEQ } from './modules/local/multiqc/main'
include { BUILD_RAW_EXPRESSION_BUNDLE } from './modules/local/build_raw_expression_bundle/main'
include { PREPARE_AFFYMETRIX } from './modules/local/prepare_affymetrix/main'
include { BUILD_MICROARRAY_EXPRESSION_BUNDLE } from './modules/local/build_microarray_expression_bundle/main'

params.outdir = params.outdir ?: 'results'
params.reference_cache = params.reference_cache ?: '.transcriptforge-reference-cache'
params.reference_cache_uri = params.reference_cache_uri ?: null
params.prepared_dataset_id = params.prepared_dataset_id ?: null
params.prepared_version = params.prepared_version ?: null
params.reference_asset_dir = params.reference_asset_dir ?: null

process PHASE0_SMOKE {
    tag 'phase0-smoke'
    label 'process_low'
    container 'alpine:3.21'

    publishDir "${params.outdir}/phase0-smoke", mode: 'copy', overwrite: true

    output:
    path 'health.json', emit: health

    script:
    """
    cat > health.json <<'EOF'
    {
      "status": "ok",
      "component": "transcriptforge-nextflow",
      "schema_version": "1.0.0"
    }
    EOF
    """
}

workflow VALIDATE_DATASET {
    if (!params.validation_config || !params.matrix || !params.metadata) {
        error 'PREPARE_DATASET requires --validation_config, --matrix, and --metadata.'
    }

    validation_config_ch = Channel.fromPath(params.validation_config, checkIfExists: true)
    matrix_ch = Channel.fromPath(params.matrix, checkIfExists: true)
    metadata_ch = Channel.fromPath(params.metadata, checkIfExists: true)
    analysis_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )

    VALIDATE_COUNT_MATRIX(
        validation_config_ch,
        matrix_ch,
        metadata_ch,
        analysis_package_ch
    )

    emit:
    validation_report = VALIDATE_COUNT_MATRIX.out.report
    dataset_manifest = VALIDATE_COUNT_MATRIX.out.manifest
}

workflow PREPARE_DATASET {
    if (!params.validation_config || !params.matrix || !params.metadata) {
        error 'PREPARE_DATASET requires --validation_config, --matrix, and --metadata.'
    }

    validation_config_ch = Channel.fromPath(params.validation_config, checkIfExists: true)
    matrix_ch = Channel.fromPath(params.matrix, checkIfExists: true)
    metadata_ch = Channel.fromPath(params.metadata, checkIfExists: true)
    validation_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )
    bundle_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )

    VALIDATE_COUNT_MATRIX(
        validation_config_ch,
        matrix_ch,
        metadata_ch,
        validation_package_ch
    )

    BUILD_EXPRESSION_BUNDLE(
        validation_config_ch,
        matrix_ch,
        metadata_ch,
        VALIDATE_COUNT_MATRIX.out.report,
        VALIDATE_COUNT_MATRIX.out.manifest,
        bundle_package_ch
    )

    emit:
    validation_report = VALIDATE_COUNT_MATRIX.out.report
    dataset_manifest = VALIDATE_COUNT_MATRIX.out.manifest
    expression_bundle = BUILD_EXPRESSION_BUNDLE.out.archive
    bundle_manifest = BUILD_EXPRESSION_BUNDLE.out.manifest
    bundle_summary = BUILD_EXPRESSION_BUNDLE.out.summary
    qc_summary = BUILD_EXPRESSION_BUNDLE.out.qc
    feature_mapping_summary = BUILD_EXPRESSION_BUNDLE.out.mapping
}

workflow RUN_ANALYSIS {
    if (!params.analysis_request || !params.expression_bundle) {
        error 'RUN_ANALYSIS requires --analysis_request and --expression_bundle.'
    }

    request_ch = Channel.fromPath(params.analysis_request, checkIfExists: true)
    bundle_ch = Channel.fromPath(params.expression_bundle, checkIfExists: true)
    analysis_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )
    analysis_r_ch = Channel.fromPath(
        "${projectDir}/../analysis/r",
        type: 'dir',
        checkIfExists: true
    )
    def analysisRequest = new groovy.json.JsonSlurper().parse(new File(params.analysis_request))

    if (analysisRequest.analysis_type == 'differential_expression') {
        RUN_DIFFERENTIAL_EXPRESSION(request_ch, bundle_ch, analysis_r_ch)
    } else if (analysisRequest.analysis_type == 'dimension_reduction') {
        RUN_DIMENSION_REDUCTION(request_ch, bundle_ch, analysis_package_ch)
    } else if (analysisRequest.analysis_type == 'signature') {
        if (analysisRequest.method in ['gsva', 'ssgsea']) {
            RUN_GSVA_SCORING(request_ch, bundle_ch, analysis_r_ch)
        } else {
            RUN_SIGNATURE_SCORING(request_ch, bundle_ch, analysis_package_ch)
        }
    } else {
        error "Unsupported analysis type: ${analysisRequest.analysis_type}"
    }
}

workflow PREPARE_RAW_RNASEQ {
    if (!params.ingestion_manifest || !params.reference_definition || !params.reads) {
        error 'PREPARE_RAW_RNASEQ requires --ingestion_manifest, --reference_definition, and --reads.'
    }
    if (!params.reference_cache || !params.prepared_dataset_id || !params.prepared_version) {
        error 'PREPARE_RAW_RNASEQ requires reference cache and prepared-dataset identity parameters.'
    }

    ingestion_ch = Channel.fromPath(params.ingestion_manifest, checkIfExists: true)
    reference_ch = Channel.fromPath(params.reference_definition, checkIfExists: true)
    reads_ch = Channel.fromPath(params.reads, type: 'dir', checkIfExists: true)
    reference_assets_ch = params.reference_asset_dir
        ? Channel.fromPath(params.reference_asset_dir, type: 'dir', checkIfExists: true)
        : Channel.value([])
    analysis_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )
    analysis_r_ch = Channel.fromPath(
        "${projectDir}/../analysis/r",
        type: 'dir',
        checkIfExists: true
    )

    VERIFY_RAW_INPUTS(ingestion_ch, reference_ch, reads_ch, analysis_package_ch)
    MATERIALIZE_SALMON_REFERENCE(reference_ch, analysis_package_ch, reference_assets_ch)

    sample_reads_ch = VERIFY_RAW_INPUTS.out.manifest.flatMap { manifest ->
        def payload = new groovy.json.JsonSlurper().parse(manifest)
        payload.samples.collect { sample ->
            tuple(
                sample.sample_id as String,
                file(sample.read1 as String, checkIfExists: true),
                sample.read2 ? file(sample.read2 as String, checkIfExists: true) : [],
                payload.salmon_library_type as String,
                sample.read2 != null
            )
        }
    }
    FASTQC_READS(sample_reads_ch)
    FASTP_TRIM(sample_reads_ch)
    salmon_index_ch = MATERIALIZE_SALMON_REFERENCE.out.index.first()
    SALMON_QUANT(FASTP_TRIM.out.reads, salmon_index_ch)

    TXIMPORT_GENE_SUMMARIES(
        SALMON_QUANT.out.quant.map { sample_id, quant -> quant }.collect(),
        MATERIALIZE_SALMON_REFERENCE.out.tx2gene,
        VERIFY_RAW_INPUTS.out.manifest,
        analysis_r_ch
    )
    qc_inputs_ch = FASTQC_READS.out.results.map { sample_id, results -> results }
        .mix(FASTP_TRIM.out.reports.map { sample_id, json, html -> [json, html] })
        .mix(SALMON_QUANT.out.quant.map { sample_id, quant -> quant })
        .collect()
    MULTIQC_RAW_RNASEQ(qc_inputs_ch)
    BUILD_RAW_EXPRESSION_BUNDLE(
        VERIFY_RAW_INPUTS.out.manifest,
        TXIMPORT_GENE_SUMMARIES.out.counts,
        TXIMPORT_GENE_SUMMARIES.out.tpm,
        TXIMPORT_GENE_SUMMARIES.out.transcript_tpm,
        TXIMPORT_GENE_SUMMARIES.out.qc_metrics,
        TXIMPORT_GENE_SUMMARIES.out.qc_summary,
        VERIFY_RAW_INPUTS.out.metadata,
        analysis_package_ch
    )

    emit:
    expression_bundle = BUILD_RAW_EXPRESSION_BUNDLE.out.archive
    bundle_manifest = BUILD_RAW_EXPRESSION_BUNDLE.out.manifest
    bundle_summary = BUILD_RAW_EXPRESSION_BUNDLE.out.summary
    multiqc_report = MULTIQC_RAW_RNASEQ.out.report
    reference_materialization = MATERIALIZE_SALMON_REFERENCE.out.manifest
    gene_counts = TXIMPORT_GENE_SUMMARIES.out.counts
    gene_tpm = TXIMPORT_GENE_SUMMARIES.out.tpm
    transcript_counts = TXIMPORT_GENE_SUMMARIES.out.transcript_counts
    transcript_tpm = TXIMPORT_GENE_SUMMARIES.out.transcript_tpm
    salmon_quantifications = TXIMPORT_GENE_SUMMARIES.out.salmon_quantifications
    raw_qc_metrics = TXIMPORT_GENE_SUMMARIES.out.qc_metrics
    raw_qc_summary = TXIMPORT_GENE_SUMMARIES.out.qc_summary
}

workflow PREPARE_AFFYMETRIX_CEL {
    if (!params.ingestion_manifest || !params.cels || !params.metadata) {
        error 'PREPARE_AFFYMETRIX_CEL requires --ingestion_manifest, --cels, and --metadata.'
    }
    if (!params.prepared_dataset_id || !params.prepared_version) {
        error 'PREPARE_AFFYMETRIX_CEL requires prepared-dataset identity parameters.'
    }

    ingestion_ch = Channel.fromPath(params.ingestion_manifest, checkIfExists: true)
    cels_ch = Channel.fromPath(params.cels, type: 'dir', checkIfExists: true)
    metadata_ch = Channel.fromPath(params.metadata, checkIfExists: true)
    analysis_package_ch = Channel.fromPath(
        "${projectDir}/../analysis/python/transcriptforge_analysis",
        type: 'dir',
        checkIfExists: true
    )
    analysis_r_ch = Channel.fromPath(
        "${projectDir}/../analysis/r",
        type: 'dir',
        checkIfExists: true
    )

    PREPARE_AFFYMETRIX(ingestion_ch, cels_ch, analysis_r_ch)
    BUILD_MICROARRAY_EXPRESSION_BUNDLE(
        ingestion_ch,
        PREPARE_AFFYMETRIX.out.results,
        metadata_ch,
        analysis_package_ch
    )

    emit:
    expression_bundle = BUILD_MICROARRAY_EXPRESSION_BUNDLE.out.archive
    bundle_manifest = BUILD_MICROARRAY_EXPRESSION_BUNDLE.out.manifest
    bundle_summary = BUILD_MICROARRAY_EXPRESSION_BUNDLE.out.summary
    rma_outputs = PREPARE_AFFYMETRIX.out.results
}

workflow RUN_DEMO {
    PHASE0_SMOKE()
}

workflow PREDICT_WITH_MODEL {
    error 'PREDICT_WITH_MODEL is planned for classifier development.'
}
