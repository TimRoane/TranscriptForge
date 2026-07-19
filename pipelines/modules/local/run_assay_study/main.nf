process RUN_PRECISION_REPRODUCIBILITY_STUDY {
    tag 'precision-reproducibility-study'
    label 'process_medium'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/study", mode: 'copy', overwrite: true

    input:
    path study_spec
    path study_assignments
    path expression_bundle
    path model
    path model_manifest
    path analysis_package
    path validation_contracts

    output:
    path 'results/validation_bundle', emit: bundle
    path 'results/validation_bundle.tar.gz', emit: archive

    script:
    """
    TRANSCRIPTFORGE_VALIDATION_CONTRACT_ROOT=${validation_contracts} \
    PYTHONPATH=. ${params.analysis_python} -m transcriptforge_analysis.precision_study_cli \
      --study-spec ${study_spec} \
      --assignments ${study_assignments} \
      --bundle ${expression_bundle} \
      --model ${model} \
      --model-manifest ${model_manifest} \
      --output-dir results
    """
}
