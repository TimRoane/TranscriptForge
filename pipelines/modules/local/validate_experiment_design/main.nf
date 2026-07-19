process VALIDATE_EXPERIMENT_DESIGN {
    tag 'validate-experiment-design'
    label 'process_low'
    container 'python:3.12-slim'

    publishDir "${params.outdir}/experiment/design", mode: 'copy', overwrite: true

    input:
    path experiment_spec
    path experiment_assignments
    path experiment_schema
    path analysis_package

    output:
    path 'design_validation.json', emit: validation

    script:
    """
    PYTHONPATH=. ${params.analysis_python} -m transcriptforge_analysis.experiment_design_cli \
      --spec ${experiment_spec} \
      --assignments ${experiment_assignments} \
      --schema ${experiment_schema} \
      --output design_validation.json
    """
}
