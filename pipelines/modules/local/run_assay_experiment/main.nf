process RUN_INPUT_DEGRADATION_EXPERIMENT {
    tag 'development-experiment'
    label 'process_medium'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/experiment", mode: 'copy', overwrite: true

    input:
    path experiment_spec
    path experiment_assignments
    path expression_bundle
    path design_validation
    path analysis_package

    output:
    path 'results/development_evidence_bundle', emit: bundle
    path 'results/development_evidence_bundle.tar.gz', emit: archive

    script:
    """
    test -s ${design_validation}
    PYTHONPATH=. ${params.analysis_python} -m transcriptforge_analysis.assay_experiment_cli \
      --spec ${experiment_spec} \
      --assignments ${experiment_assignments} \
      --bundle ${expression_bundle} \
      --output-dir results
    """
}
