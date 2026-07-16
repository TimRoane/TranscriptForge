nextflow.enable.dsl = 2

include { VALIDATE_COUNT_MATRIX } from './modules/local/validate_matrix/main'
include { BUILD_EXPRESSION_BUNDLE } from './modules/local/build_expression_bundle/main'
include { RUN_DIMENSION_REDUCTION } from './modules/local/run_pca/main'
include { RUN_DIFFERENTIAL_EXPRESSION } from './modules/local/run_differential_expression/main'

params.outdir = params.outdir ?: 'results'

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
    } else {
        error "Unsupported analysis type: ${analysisRequest.analysis_type}"
    }
}

workflow RUN_DEMO {
    PHASE0_SMOKE()
}

workflow PREDICT_WITH_MODEL {
    error 'PREDICT_WITH_MODEL is planned for classifier development.'
}
