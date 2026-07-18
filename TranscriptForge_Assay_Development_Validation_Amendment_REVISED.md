# TranscriptForge
## Codex Plan Amendment v2: Guided RNA Assay Development, Experiment Design, and Analytical Validation

**Base plan:** `TranscriptForge_Codex_Implementation_Plan.md`  
**Replaces:** `TranscriptForge_Assay_Development_Validation_Amendment.md`  
**Status:** Additive amendment; the base implementation plan remains authoritative unless this document explicitly extends it.  
**Primary purpose:** Extend TranscriptForge into an easy-to-use, question-first RNA assay-development workbench that helps a scientist determine what to do next, design defensible experiments, analyze the resulting data, preserve decisions and rationale, develop and lock an RNA signature or classifier, and run traceable analytical-validation studies.

---

## 0. Non-Negotiable Product Directive

TranscriptForge must not become merely a collection of RNA analysis menus.

The default experience must answer five questions at every stage:

1. **Where am I in assay development?**
2. **What question should I answer next?**
3. **What experiment should I run to answer it?**
4. **What did the results show?**
5. **What is the next scientifically defensible action?**

The primary user experience is therefore:

```text
Define the assay-development problem
        ↓
Assess readiness and unresolved risks
        ↓
Choose a plain-language scientific question
        ↓
Construct and validate an experiment design
        ↓
Run or import the experiment
        ↓
Analyze molecular, technical, and algorithmic endpoints
        ↓
Summarize the decision and limitations
        ↓
Recommend the next experiment or milestone
        ↓
Require the scientist to approve, reject, or modify that recommendation
```

The software may recommend. It must not silently make scientific decisions.

---

## 1. Relationship to the Base Plan

Codex must read and preserve `TranscriptForge_Codex_Implementation_Plan.md` before implementing this amendment.

The following base-plan decisions remain authoritative:

- Dataset preparation and downstream analysis remain separate run types.
- Every prepared dataset remains an immutable canonical Expression Bundle.
- Standard exploratory and model-development analyses continue to emit Result Bundles.
- Nextflow DSL2 owns scientific execution.
- FastAPI, Celery, PostgreSQL, Redis, and the React GUI coordinate work but do not contain hidden scientific calculations.
- Scientific calculations remain containerized, testable R or Python package functions behind thin CLI wrappers.
- Frozen JSON or YAML configuration, checksums, container digests, software versions, reference versions, random seeds, and provenance remain mandatory.
- Existing differential-expression, dimensionality-reduction, signature, classifier, and deconvolution modules remain reusable scientific building blocks.
- TranscriptForge remains a research and portfolio product and must not claim that its output is a clinically validated diagnostic result.

This amendment adds three concepts around the existing architecture:

1. **Assay Development Project** — the stage-aware guided workspace.
2. **Development Experiment** — a pre-lock experiment used for feasibility, optimization, and scientific learning.
3. **Analytical Study** — a post-lock, prespecified evaluation of a fixed assay endpoint.

The resulting scientific run categories are:

```text
Source data
    ↓
PREPARE_DATASET
    ↓
Immutable Expression Bundle

Expression Bundle
    ↓
RUN_ANALYSIS
    ↓
Exploration / DE / signature / classifier / deconvolution
    ↓
Result Bundle

Expression Bundles + ExperimentSpec + optional candidate endpoint
    ↓
RUN_ASSAY_EXPERIMENT
    ↓
Development Evidence Bundle

Accepted classifier candidate
    ↓
LOCK_MODEL
    ↓
Immutable ModelManifest

Expression Bundles + locked ModelManifest + StudySpec
    ↓
RUN_ASSAY_STUDY
    ↓
Validation Bundle
```

`RUN_ASSAY_EXPERIMENT` and `RUN_ASSAY_STUDY` must remain distinct:

- A development experiment may be iterative and may inform changes.
- A validation study evaluates a locked endpoint and must not retrain or silently alter it.

---

## 2. Product Goal

TranscriptForge must support this practical workflow:

```text
DEFINE
  Clarify the proposed purpose, specimen, output, and available evidence
        ↓
FEASIBILITY
  Determine whether intended samples can produce usable RNA measurements
        ↓
EXPLORE
  Understand biology, technical variation, batch effects, and confounders
        ↓
OPTIMIZE
  Compare wet-lab and analytical conditions and reduce avoidable variability
        ↓
DEVELOP
  Build and evaluate a signature or classifier without leakage
        ↓
LOCK
  Freeze preprocessing, features, model, threshold, QC expectations, and versions
        ↓
VALIDATE
  Evaluate precision, input/degradation limits, bridging, robustness, and interference
        ↓
REPORT
  Assemble evidence, criteria, limitations, decisions, provenance, and next actions
```

The platform must help answer questions such as:

- Do the proposed specimens yield enough usable RNA measurements to continue development?
- Which library-preparation or sequencing condition performs best?
- Is an apparent biological signal actually explained by batch, site, degradation, tumor content, or cell composition?
- What additional samples or replicates are required before a conclusion is supportable?
- Is there enough signal to begin classifier development?
- Is a classifier candidate ready to lock?
- Is the locked score repeatable within and between runs?
- How much variation is attributable to biological sample, operator, lot, instrument, site, or run?
- Does lower RNA input or greater degradation destabilize the score or final call?
- Is a proposed pipeline or reagent change equivalent to the current version within a prespecified margin?
- Does a realistic interference or robustness challenge cause unacceptable bias or call changes?
- Are disagreements concentrated near the decision threshold?
- What is the most defensible next action after the experiment finishes?

---

## 3. Explicit Non-Goals

Do not turn TranscriptForge into a universal diagnostic-development, clinical-trial, LIMS, or regulatory platform.

Version 1 of this expansion must not:

- Claim FDA, IVDR, CAP, CLIA, ISO 13485, IEC 62304, or other regulatory compliance.
- Automatically determine clinical validity or clinical utility.
- Automatically invent intended use, specimen requirements, clinical claims, or acceptance thresholds.
- Generate a statement that an assay is safe, effective, approved, cleared, or clinically validated.
- Replace a pathologist, wet-lab assay scientist, clinical biostatistician, Quality, Regulatory, or medical director.
- Support arbitrary clinical-trial, adaptive-trial, survival-analysis, or longitudinal treatment-response programs.
- Manage specimen accessioning, chain of custody, clinical report authorization, or billing.
- Treat synthetic data as evidence about a real assay.
- Treat an expression-classifier input study as a formal limit-of-detection study unless the endpoint and design genuinely justify that terminology.
- Allow a model, feature set, normalization method, threshold, input file, or StudySpec to change silently after lock.
- Present a rule-engine recommendation as a scientific conclusion without showing its evidence and assumptions.

Preferred language:

- development experiment
- feasibility experiment
- optimization experiment
- analytical study
- verification study
- validation-style evidence
- research use only
- prespecified acceptance criterion
- minimum supported input under demonstrated conditions
- recommended next action
- scientist decision required

Avoid:

- FDA-ready
- regulatory compliant
- clinically validated
- approved diagnostic
- established clinical limit of detection
- autonomous assay design

---

## 4. Primary User Experience: The Guided Assay Development Workspace

The guided workspace is the default entry point for an Assay Development Project.

Expert users may still directly open datasets, analyses, models, experiments, or studies. The default guided experience must not require the user to know the formal statistical or regulatory vocabulary before beginning.

### 4.1 Project dashboard

The top of every Assay Development Project must show:

```text
Current stage
Overall readiness status
Current scientific question
What is known
What remains unresolved
Blocking issues
Recommended next action
Alternative actions
Recent evidence and decisions
```

Example:

```text
Current stage: FEASIBILITY

Current question
Can the intended FFPE specimens produce stable classifier-ready RNA measurements?

Known
✓ 42 specimens have expression data
✓ RNA input and DV200 are recorded
✓ Sequencing QC is available

Unresolved
⚠ No technical replicates are present
⚠ Reagent lot is missing for 11 measurements
⚠ Low-input samples are concentrated in one sequencing run

Recommended next action
Create a balanced input/degradation feasibility experiment.

Why
Input and degradation vary substantially, but their effects cannot currently be
separated from sequencing run.

Alternatives
- Import missing reagent-lot metadata first
- Continue exploratory analysis with an unresolved-confounding warning

Not recommended
- Begin classifier lock
```

### 4.2 Five-question stage card

Every stage page must show:

1. **Question:** What is being decided?
2. **Requirements:** What data, metadata, controls, and replication are needed?
3. **Action:** What experiment or analysis should be run?
4. **Evidence:** What has already been learned?
5. **Next decision:** What must the scientist approve?

### 4.3 Progress is evidence-based, not a rigid checklist

A project may move backward or repeat a stage.

Examples:

- A classifier-development result may reveal unresolved batch confounding and return the project to `OPTIMIZE`.
- A precision study may fail because of one reagent lot and create a new optimization experiment.
- A bridging study may identify systematic bias and prevent release of the candidate change.

Stage transitions must be recommendations approved by the user, not automatic irreversible state changes.

---

## 5. Assay Development Lifecycle State Machine

Add the following project stages:

```text
DEFINE
FEASIBILITY
EXPLORE
OPTIMIZE
DEVELOP
LOCK
VALIDATE
REPORT
ON_HOLD
COMPLETED
```

Each stage has readiness checks and supported next actions.

### 5.1 DEFINE

Purpose:

- Capture the proposed assay-development problem.
- Record intended specimen and proposed output.
- Record available samples, truth labels, and known constraints.
- Make assumptions visible.

Required user decisions:

- proposed purpose
- specimen type
- biological system or disease context
- proposed endpoint or output
- available truth or reference label
- important false-positive and false-negative consequences, when known

TranscriptForge does not judge whether the proposed intended use is clinically appropriate.

### 5.2 FEASIBILITY

Purpose:

- Determine whether the proposed specimens and measurement method generate usable RNA data.
- Identify basic input, quality, yield, mapping, detection, and stability limitations.

Typical questions:

- Can RNA be recovered consistently?
- Are expression profiles stable enough for downstream analysis?
- Which sample-quality variables predict failure?
- Is more technical replication required?

### 5.3 EXPLORE

Purpose:

- Characterize biological signal, technical variation, batch effects, outliers, and cell composition.

Typical analyses:

- PCA and other dimensionality reduction
- differential expression
- sample correlation
- batch and site stratification
- deconvolution
- outcome and covariate associations

### 5.4 OPTIMIZE

Purpose:

- Compare candidate wet-lab or computational conditions.
- Reduce avoidable technical variation before model lock.

Examples:

- extraction method A versus B
- library preparation A versus B
- sequencing depth levels
- RNA input levels during development
- normalization candidates
- QC-filter candidates
- candidate feature sets

Optimization results may influence the assay or model. They are not validation evidence for a locked product.

### 5.5 DEVELOP

Purpose:

- Develop a signature or classifier using leakage-resistant methods.
- Evaluate internal or external performance.
- Review calibration, threshold behavior, subgroup performance, and feature stability.

### 5.6 LOCK

Purpose:

- Freeze the prediction package and analytical assumptions.
- Verify deterministic inference.
- Prevent changes during analytical validation.

### 5.7 VALIDATE

Purpose:

- Evaluate a locked endpoint through supported precision, input/degradation, bridging, robustness, and interference templates.

### 5.8 REPORT

Purpose:

- Assemble a traceable evidence package.
- Record unresolved risks and limitations.
- Preserve scientist decisions and next-action rationale.

---

## 6. New Domain Model

### 6.1 `AssayDevelopmentProject`

Add a domain entity linked one-to-one or one-to-many with the existing `Project`, depending on the base implementation.

Suggested fields:

```text
id
project_id
name
proposed_purpose
specimen_type
biological_context
proposed_output
current_stage
readiness_status
active_question_id nullable
assay_version nullable
created_by
created_at
updated_at
completed_at nullable
```

Readiness status enum:

```text
NOT_ASSESSED
BLOCKED
NEEDS_INFORMATION
READY_FOR_RECOMMENDED_ACTION
ACTION_IN_PROGRESS
REVIEW_REQUIRED
```

### 6.2 `ScientificQuestion`

Represents the question currently being answered.

```text
id
assay_project_id
question_key
plain_language_question
formal_question
stage
status
source
created_at
resolved_at nullable
resolution_summary nullable
```

Question source:

```text
USER_SELECTED
SYSTEM_RECOMMENDED
FOLLOW_UP_FROM_RESULT
```

### 6.3 `ExperimentPlan`

Represents a pre-lock feasibility or optimization experiment.

```text
id
assay_project_id
question_id
name
experiment_type
objective
status
experiment_spec_uri
experiment_spec_sha256 nullable
development_bundle_uri nullable
current_revision
created_by
created_at
updated_at
locked_at nullable
completed_at nullable
```

Status:

```text
DRAFT
DESIGN_VALID
DESIGN_INVALID
LOCKED_FOR_EXECUTION
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUPERSEDED
```

`LOCKED_FOR_EXECUTION` freezes that execution revision but does not imply the assay or model is locked. A changed experiment requires a cloned revision.

### 6.4 `ExperimentInput`

```text
id
experiment_id
input_type
prepared_dataset_id nullable
analysis_run_id nullable
external_file_uri nullable
role
sha256 nullable
metadata_json
created_at
```

### 6.5 `DecisionRecord`

Every material scientist decision must be preserved.

```text
id
assay_project_id
source_type
source_id
stage
decision_key
decision
rationale
selected_option
alternatives_json
evidence_refs_json
made_by
made_at
supersedes_decision_id nullable
```

Examples:

- approve recommended experiment
- reject recommendation
- accept unresolved warning
- advance to model development
- lock a classifier candidate
- repeat a failed condition
- do not advance a candidate pipeline change

### 6.6 `Recommendation`

Recommendations must be persisted and reproducible.

```text
id
assay_project_id
source_type
source_id
rule_id
recommendation_type
title
summary
why
stage
priority
requirement_level
status
proposed_action_json
evidence_refs_json
assumptions_json
limitations_json
created_at
resolved_at nullable
```

Requirement level:

```text
BLOCKER
STRONGLY_RECOMMENDED
RECOMMENDED
OPTIONAL
NOT_RECOMMENDED
```

Recommendation status:

```text
OPEN
ACCEPTED
REJECTED
MODIFIED
SUPERSEDED
COMPLETED
```

### 6.7 Existing `Study` domain

Retain and extend the original amendment’s post-lock `Study`, `StudyInput`, `AcceptanceCriterion`, and `ValidationResult` entities.

A Study remains a prespecified evaluation of a locked endpoint.

---

## 7. Question-First Experiment Wizard

The wizard must begin with a plain-language question, not a statistical test.

### 7.1 Question catalog

Initial supported questions:

#### DEFINE / FEASIBILITY

- Can the intended specimens produce usable RNA data?
- Which sample-quality variables predict technical failure?
- Do we need more technical replicates?
- Does RNA input or degradation affect expression stability?

#### EXPLORE

- What is the largest source of variation?
- Is the outcome signal distinguishable from batch or site?
- Are outliers biological or technical?
- Is cell composition affecting the observed signal?

#### OPTIMIZE

- Which extraction or library-preparation condition performs best?
- What sequencing depth is sufficient for stable endpoints?
- Which normalization or preprocessing approach is most stable?
- Which QC rule best identifies unreliable measurements?

#### DEVELOP

- Is there enough stable signal to build a classifier?
- Which candidate model generalizes best?
- Is the model calibrated?
- Is the selected threshold stable and defensible?
- Is the classifier ready to lock?

#### VALIDATE

- Is the locked score repeatable and reproducible?
- What is the lowest supported input under tested conditions?
- Is the candidate pipeline or assay change equivalent to the comparator?
- Does a challenge condition cause unacceptable bias or call changes?

### 7.2 Question routing

Map each plain-language question to:

- lifecycle stage
- required inputs
- supported design templates
- required metadata
- recommended endpoints
- design checks
- compatible analyses
- possible next actions

Example:

```text
Question:
Which library-preparation method performs best?

Route:
Stage: OPTIMIZE
Experiment type: PAIRED_CONDITION_COMPARISON
Preferred design: same biological samples under each method
Primary endpoints: detected genes, mapping rate, expression correlation,
candidate signature score, failure rate
Required metadata: biological_sample_id, method, run, operator, lot
Potential blockers: method confounded with run or operator
```

### 7.3 Wizard steps

1. Select or write the scientific question.
2. Confirm the lifecycle stage.
3. Select available datasets or register a planned wet-lab experiment.
4. Select the primary endpoint.
5. Select the factor or condition being changed.
6. Identify what remains fixed.
7. Map biological samples, measurements, replicates, pairs, batches, operators, lots, instruments, sites, and runs.
8. Choose reference and comparator conditions.
9. Review recommended randomization and blocking.
10. Define success criteria or mark them as exploratory.
11. Review design errors, warnings, and missing information.
12. Review the generated ExperimentSpec or StudySpec.
13. Freeze the execution revision.
14. Export a wet-lab execution sheet, import results, or launch the analysis.

### 7.4 Educational guidance

Every wizard step must include:

- **What this means**
- **Why it matters**
- **Example**
- **What happens if it is missing**

Do not bury critical scientific assumptions in tooltips alone. Include them on the final review page.

---

## 8. Assay Project Readiness Engine

The readiness engine is deterministic and stage-aware.

It evaluates metadata, completed work, unresolved warnings, prior decisions, and result summaries.

### 8.1 Readiness output

Produce:

```json
{
  "stage": "FEASIBILITY",
  "status": "NEEDS_INFORMATION",
  "ready_items": [],
  "missing_items": [],
  "blockers": [],
  "warnings": [],
  "recommended_action_ids": [],
  "alternative_action_ids": [],
  "not_recommended_action_ids": []
}
```

### 8.2 Examples of readiness rules

```text
IF no specimen type is recorded
THEN block feasibility planning and request specimen context

IF no sample-level RNA quality metric exists
THEN recommend collecting or importing one before an input/degradation experiment

IF outcome is perfectly aligned with batch
THEN block classifier lock and recommend a rebalanced experiment or independent cohort

IF no repeated measurements exist
THEN do not claim repeatability can be estimated

IF classifier performance is weak or unstable across folds
THEN do not recommend model lock

IF calibration is poor
THEN recommend calibration and threshold review before lock

IF model assets are incomplete or inference is nondeterministic
THEN block model lock

IF a validation design is non-identifiable
THEN block execution

IF a design is merely unbalanced but estimable
THEN warn and explain the consequence rather than rejecting it automatically
```

### 8.3 Rule transparency

Every readiness item must show:

- rule ID
- input facts used
- conclusion
- severity
- action suggested
- assumptions
- documentation link

No hidden scoring model should control stage readiness in version 1.

---

## 9. Next-Best-Action Engine

The next-best-action engine converts readiness and completed result summaries into controlled recommendations.

### 9.1 Recommendation contract

Every recommendation must contain:

```text
Title
What to do
Why it is recommended
Evidence supporting it
What it will resolve
Required inputs
Expected output
Known limitations
Priority
Requirement level
Alternative actions
One-click action template
Scientist decision required
```

### 9.2 Initial rule families

#### Design rules

- Confounded factor → rebalance or collect additional measurements.
- Missing reference condition → add reference before comparative inference.
- No biological pairing → avoid paired analysis.
- Insufficient repeated measurements → add replicates or limit conclusions.
- Non-estimable factor → remove it or redesign.

#### Feasibility rules

- High technical failure rate → investigate failure predictors before classifier development.
- Expression instability associated with DV200/input → create focused input/degradation experiment.
- Sequencing depth plateau observed → consider lower depth confirmation.

#### Exploration rules

- Batch dominates PCA and aligns with outcome → resolve confounding before classifier development.
- Cell composition explains candidate signal → inspect deconvolution-adjusted and unadjusted results.
- Outlier group shares a technical factor → create a targeted root-cause experiment.

#### Model-development rules

- Leakage trap detected → invalidate candidate run.
- External validation unavailable → label internal validation and recommend external cohort acquisition.
- Feature stability is poor → revise feature selection or collect more data.
- Calibration poor but discrimination acceptable → review calibration strategy.
- Threshold-adjacent instability high → enrich follow-up data near the threshold before lock.

#### Validation rules

- Precision fails because of one identifiable factor → investigate that factor before broad redesign.
- High score correlation but systematic bias → do not pass bridging on correlation alone.
- Input level passes only one isolated level → require confirmation at consecutive levels.
- Challenge effect is significant but below the declared margin → report effect and criterion result separately.
- Disagreements cluster near threshold → recommend targeted threshold-adjacent follow-up.

### 9.3 Human control

The user must explicitly:

- accept the recommendation
- reject it with rationale
- modify it into a new action
- defer it

Acceptance may create a draft ExperimentSpec, AnalysisRequest, or StudySpec. It must never launch automatically.

---

## 10. Development Experiment Domain and Contract

A Development Experiment is a controlled pre-lock experiment intended to learn, compare, or optimize.

### 10.1 Supported initial experiment types

```text
TECHNICAL_FEASIBILITY
PAIRED_CONDITION_COMPARISON
MULTIFACTOR_OPTIMIZATION
INPUT_DEGRADATION_EXPLORATION
SEQUENCING_DEPTH_EXPLORATION
VARIANCE_SOURCE_INVESTIGATION
QC_RULE_EVALUATION
BATCH_CONFOUNDER_INVESTIGATION
```

Do not support arbitrary experimental designs in version 1. Reject unsupported designs with a clear explanation and suggested simplification.

### 10.2 `ExperimentSpec`

Store the normalized, immutable execution revision as YAML or JSON.

Example:

```yaml
schema_version: "1.0"
experiment:
  experiment_id: exp_2026_001
  name: FFPE RNA input feasibility
  type: INPUT_DEGRADATION_EXPLORATION
  stage: FEASIBILITY
  objective: >-
    Determine whether RNA input and degradation are associated with unstable
    expression measurements under the tested conditions.
  exploratory: true

assay_context:
  specimen_type: ffpe_tumor
  proposed_output: expression_classifier_score
  assay_version: development-unlocked

question:
  plain_language: Can lower RNA input or poorer DV200 destabilize the expression endpoint?
  decision_to_inform: Whether to continue with 25 ng as a candidate development condition.

inputs:
  assignment_table: design/experiment_assignments.tsv
  expression_bundles:
    - prepared_dataset_id: prepared_001
      role: development

sample_structure:
  measurement_id: measurement_id
  biological_sample_id: biological_sample_id
  replicate_id: replicate_id
  pair_id: biological_sample_id

factors:
  - name: input_ng
    type: ordered_numeric
    role: primary
  - name: dv200
    type: continuous
    role: covariate
  - name: sequencing_run
    type: categorical
    role: blocking
  - name: operator
    type: categorical
    role: blocking

endpoints:
  primary:
    - expression_profile_correlation_to_reference
    - detected_genes
  secondary:
    - mapping_rate
    - library_complexity
    - candidate_signature_score

analysis_plan:
  template: ordered_level_paired_exploration
  reference_level: 100
  confidence_level: 0.95
  missing_value_policy: fail_required_endpoint

success_guidance:
  mode: exploratory
  declared_questions:
    - Is profile correlation stable through 25 ng?
    - Do technical failure rates increase below 25 ng?

rationales:
  reference_level: Highest routinely available input condition.
  endpoint_choice: Profile stability is required before classifier development.
```

### 10.3 Planned versus completed experiments

Support two modes:

1. **Plan-first:** Generate assignment and wet-lab execution sheets before data exist.
2. **Analyze-existing:** Map completed measurements to an experiment design after data are available.

Clearly label retrospective design mapping and warn that randomization and blocking cannot be repaired after execution.

### 10.4 Wet-lab execution package

For a planned experiment, export:

```text
experiment_execution_package/
├── experiment_spec.yaml
├── sample_assignment.csv
├── randomization_schedule.csv
├── plate_or_batch_layout.csv
├── required_metadata_template.csv
├── protocol_variable_checklist.md
├── acceptance_or_learning_questions.md
└── readme.md
```

Do not claim to replace an approved laboratory protocol.

---

## 11. Experiment Assignment Table

Each Development Experiment uses `experiment_assignments.tsv`.

Required:

```text
measurement_id
biological_sample_id
prepared_dataset_id
include
```

Conditionally required:

```text
replicate_id
pair_id
reference_condition
challenge_condition
input_level
operator
reagent_lot
instrument
site
run
day
plate
well
processing_order
```

Rules:

- `measurement_id` must be unique.
- Multiple measurements may map to one biological sample.
- Excluded rows remain present with `include=false` and an exclusion reason.
- Original assignment files become immutable after execution lock.
- Missing factor levels must not be silently inferred from filenames.
- The system may offer mapping suggestions but the user must confirm them.

---

## 12. Development Experiment Design Assistant

### 12.1 Shared checks

- schema validity
- input existence and checksums
- Expression Bundle validity
- measurement uniqueness
- biological sample resolution
- endpoint availability
- required factor presence
- missing-value patterns
- duplicate assignments
- reference condition availability
- planned versus observed sample count

### 12.2 Design checks

- factor confounding
- outcome/batch alignment
- paired completeness
- repeated-measure adequacy
- crossed versus nested factor structure
- rank deficiency
- empty factor combinations
- randomization imbalance
- processing-order trends
- insufficient levels for variance estimation
- reference measurements missing for challenge conditions

### 12.3 Design recommendations

The engine may recommend:

- paired rather than unpaired comparison
- blocked randomization
- balancing conditions across runs/operators/lots
- removing a non-estimable factor
- collecting additional measurements
- adding technical replicates
- adding a reference condition
- simplifying a multifactor experiment

The user approves every material design change.

### 12.4 Output

Write:

```text
design/design_validation.json
design/design_summary.md
design/factor_balance.tsv
design/confounding_matrix.tsv
design/missingness.tsv
design/recommendations.json
```

---

## 13. New Top-Level Workflow: `RUN_ASSAY_EXPERIMENT`

### 13.1 High-level Nextflow structure

```groovy
workflow RUN_ASSAY_EXPERIMENT {
    VALIDATE_EXPERIMENT_SPEC(params.experiment_spec)
    VALIDATE_EXPRESSION_BUNDLES(...)
    VALIDATE_EXPERIMENT_DESIGN(...)

    BUILD_EXPERIMENT_ENDPOINT_TABLE(...)

    if (params.experiment_type == 'technical_feasibility') {
        TECHNICAL_FEASIBILITY_ANALYSIS(...)
    } else if (params.experiment_type == 'paired_condition_comparison') {
        PAIRED_CONDITION_ANALYSIS(...)
    } else if (params.experiment_type == 'multifactor_optimization') {
        MULTIFACTOR_OPTIMIZATION_ANALYSIS(...)
    } else if (params.experiment_type == 'input_degradation_exploration') {
        INPUT_DEGRADATION_EXPLORATION(...)
    } else if (params.experiment_type == 'sequencing_depth_exploration') {
        SEQUENCING_DEPTH_EXPLORATION(...)
    } else if (params.experiment_type == 'variance_source_investigation') {
        VARIANCE_SOURCE_ANALYSIS(...)
    } else if (params.experiment_type == 'qc_rule_evaluation') {
        QC_RULE_EVALUATION(...)
    } else if (params.experiment_type == 'batch_confounder_investigation') {
        BATCH_CONFOUNDER_ANALYSIS(...)
    } else {
        error "Unsupported development experiment type"
    }

    BUILD_DEVELOPMENT_EVIDENCE_BUNDLE(...)
    GENERATE_DECISION_SUMMARY(...)
    EVALUATE_NEXT_ACTION_RULES(...)
    RENDER_DEVELOPMENT_REPORT(...)
}
```

### 13.2 Scientific process requirements

- One cohesive operation per process.
- Immutable containers and version output.
- Deterministic seeds where applicable.
- Schema and design validation before expensive computation.
- No arbitrary code from user-provided formulas.
- No automatic model retraining unless the explicit experiment type calls an existing model-development workflow.
- Preserve all inputs and excluded measurements.
- Emit trace, timeline, report, DAG, logs, versions, and checksums.
- Support local and AWS Batch profiles through configuration only.

---

## 14. Development Evidence Bundle

Every completed Development Experiment emits:

```text
development_evidence_bundle/
├── manifest.json
├── experiment_spec.yaml
├── question.json
├── design/
│   ├── experiment_assignments.tsv
│   ├── design_validation.json
│   ├── factor_balance.tsv
│   └── confounding_matrix.tsv
├── endpoints/
│   ├── endpoint_table.parquet
│   ├── endpoint_table.tsv.gz
│   └── excluded_measurements.tsv
├── results/
│   ├── primary_results.json
│   ├── secondary_results.json
│   ├── model_summaries.json
│   └── sensitivity_results.json
├── figures/
├── decision/
│   ├── decision_summary.json
│   ├── decision_summary.md
│   ├── recommendations.json
│   └── unresolved_questions.json
├── provenance/
│   ├── input_checksums.tsv
│   ├── software_versions.yml
│   ├── container_digests.tsv
│   ├── parameters.json
│   └── nextflow_metadata/
└── report/
    ├── development_report.html
    └── development_report.pdf
```

### 14.1 Decision summary contract

Every result must produce a short structured summary:

```json
{
  "question": "Does RNA input affect endpoint stability?",
  "finding": "Profiles were stable through 25 ng and degraded below 25 ng.",
  "evidence": [],
  "limitations": [],
  "criteria_mode": "exploratory",
  "condition_results": [],
  "recommended_next_action_ids": [],
  "scientist_decision_required": true
}
```

The report must lead with this summary before detailed plots.

---

## 15. Core Development Experiment Templates

### 15.1 Technical feasibility

Use for:

- success/failure rates
- RNA input and quality summaries
- mapping and assignment rates
- detected genes
- library complexity
- expression-profile reproducibility
- missingness and failure-predictor analysis

Outputs:

- feasibility scorecard
- failure-reason table
- sample-quality associations
- recommended missing metadata
- recommendation to proceed, investigate, or collect more data

The proceed recommendation must remain a user decision.

### 15.2 Paired condition comparison

Preferred when the same biological samples are measured under two or more conditions.

Analyses:

- paired endpoint differences
- confidence intervals
- Bland–Altman visualization where appropriate
- failure-rate comparison
- profile correlation
- per-sample discordance
- condition-by-quality interactions

Do not rank a method based on one metric alone. Allow the user to declare primary and secondary endpoints.

### 15.3 Multifactor optimization

Support a constrained factorial design with explicit limits.

Potential factors:

- extraction method
- library method
- input level
- operator
- lot
- instrument
- sequencing depth

Analyses:

- fixed-effect estimates
- selected interactions
- mixed-effects model for repeated biological samples
- variance decomposition
- response-surface visualization only when the design supports it

Reject overly sparse or non-identifiable designs.

### 15.4 Input/degradation exploration

This pre-lock template explores behavior and helps choose candidate conditions.

It must not automatically establish a regulatory LoD or final minimum input.

Analyses:

- ordered-level trends
- paired differences from reference
- QC deterioration
- profile stability
- candidate score stability
- threshold-crossing when a candidate model exists
- consecutive-level behavior

### 15.5 Sequencing-depth exploration

Support actual or downsampled data.

Clearly label in silico downsampling as computational simulation, not a substitute for all wet-lab effects.

Analyses:

- detected-gene saturation
- expression correlation
- signature or score stability
- classification stability
- runtime and cost estimate

### 15.6 Variance-source investigation

Use to estimate variation associated with:

- biological sample
- run
- operator
- lot
- instrument
- site
- residual

Do not imply causal attribution from a confounded observational design.

### 15.7 QC-rule evaluation

Compare candidate QC rules against measurement reliability.

Outputs:

- retained sample count
- failure capture
- endpoint stability with and without flagged samples
- false-exclusion risk indicators
- recommendation requiring human review

### 15.8 Batch-confounder investigation

Outputs:

- batch/outcome cross-tabulation
- design matrix rank
- PCA by biological and technical variables
- model sensitivity with and without batch adjustment
- clear statement of what cannot be estimated

Do not automatically batch-correct and proceed when biology and batch cannot be separated.

---

## 16. Existing Analysis and Classifier Development Integration

The guided workspace must reuse the base plan’s analyses instead of duplicating them.

Examples:

```text
Question: What is driving variation?
Action: create a guided PCA analysis request

Question: Is there a stable disease-associated expression signal?
Action: create differential-expression and confounder analyses

Question: Is cell composition affecting the signal?
Action: create deconvolution plus stratified analysis

Question: Can we build a classifier?
Action: create leakage-resistant classifier development run
```

After each `RUN_ANALYSIS`, generate a lightweight `GuidanceResult` containing:

- question answered
- important findings
- quality warnings
- unresolved risks
- recommended next actions

Do not alter the base Result Bundle schema destructively. Add optional guidance artifacts referenced by its manifest.

---

## 17. Model Lifecycle and Locking

Retain the original amendment’s locked-model architecture.

### 17.1 Model states

```text
CANDIDATE
REVIEWED
LOCKED
RETIRED
SUPERSEDED
```

Allowed transitions:

```text
CANDIDATE -> REVIEWED
REVIEWED -> LOCKED
LOCKED -> RETIRED
LOCKED -> SUPERSEDED
```

A locked model is immutable. Changes create a new candidate and lineage reference.

### 17.2 Extend `ModelRecord`

Include:

```text
status
locked_at
locked_by
parent_model_id nullable
model_manifest_uri
model_manifest_sha256
feature_schema_sha256
preprocessing_sha256
model_object_sha256
threshold_sha256
training_dataset_refs
validation_dataset_refs
container_digest
inference_test_status
```

### 17.3 ModelManifest

Must include:

- ordered feature schema
- missing-feature behavior
- imputation rules
- transformations
- scaling parameters
- normalization assumptions
- serialized model
- outcome classes
- probability interpretation
- threshold or decision rule
- expected assay and value type
- training and validation lineage
- software and container versions
- model card
- inference example and expected output
- checksums

### 17.4 Lock readiness

The guided workspace must not recommend model lock unless:

- classifier run succeeded
- leakage checks passed
- feature schema is complete
- preprocessing is serializable
- deterministic inference test passes
- threshold selection source is documented
- internal/external validation mode is clearly labeled
- unresolved critical confounding is absent or explicitly accepted
- model card is complete

### 17.5 Lock operation

1. Verify source run and assets.
2. Run inference fixture.
3. Calculate checksums.
4. Write ModelManifest atomically.
5. Store immutable model package.
6. Change status in one transaction.
7. Write audit and DecisionRecord events.
8. Recompute project readiness and next actions.

---

## 18. Post-Lock Analytical Study Domain

Retain and refine the original amendment’s `Study`, `StudyInput`, `AcceptanceCriterion`, and `ValidationResult` entities.

### 18.1 Study types

Initial supported types:

```text
PRECISION_REPRODUCIBILITY
INPUT_DEGRADATION_LIMIT
PAIRED_BRIDGING
ROBUSTNESS_INTERFERENCE
```

### 18.2 Study properties

A Study must include:

- objective
- locked model or locked signature
- immutable inputs
- study assignments
- factor structure
- endpoints
- prespecified acceptance criteria
- rationales
- design-validation result
- locked StudySpec revision

### 18.3 Study state

```text
DRAFT
DESIGN_VALID
DESIGN_INVALID
LOCKED
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUPERSEDED
```

After `LOCKED`, changes require cloning.

---

## 19. StudySpec Contract

Example:

```yaml
schema_version: "1.0"
study:
  study_id: study_2026_001
  name: Locked classifier precision study
  type: PRECISION_REPRODUCIBILITY
  objective: >-
    Evaluate repeatability and reproducibility of the locked classifier score
    and categorical call under the tested conditions.

assay_context:
  assay_name: TranscriptForge FFPE RNA demo assay
  assay_version: demo-1.0
  specimen_type: simulated_ffpe_expression
  intended_use_statement: >-
    Portfolio demonstration only. Not a clinically validated intended use.

model:
  model_id: model_2026_001
  required_status: LOCKED

inputs:
  assignment_table: design/study_assignments.tsv
  expression_bundles:
    - prepared_dataset_id: prepared_001
      role: validation

sample_structure:
  measurement_id: measurement_id
  biological_sample_id: biological_sample_id
  replicate_id: replicate_id

factors:
  - name: operator
    type: categorical
    treatment: random
  - name: reagent_lot
    type: categorical
    treatment: random
  - name: run
    type: categorical
    treatment: random

endpoints:
  continuous:
    - classifier_score
  categorical:
    - predicted_class
  qc:
    - mapping_rate
    - detected_genes

analysis_plan:
  template: crossed_random_effects
  confidence_level: 0.95
  bootstrap_iterations: 2000
  threshold_proximity_band: 0.10

acceptance_criteria:
  - key: score_icc
    metric: icc
    endpoint: classifier_score
    operator: gte
    threshold: 0.90
    rationale: Prespecified portfolio-demo criterion.
  - key: call_agreement
    metric: categorical_agreement
    endpoint: predicted_class
    operator: gte
    threshold: 0.95
    rationale: Prespecified portfolio-demo criterion.
```

All threshold and equivalence rationales must be user-provided or explicitly labeled demo defaults.

---

## 20. Study Design Validation Engine

Before lock or execution, check:

- StudySpec schema
- locked model status and checksums
- Expression Bundle compatibility
- feature-schema compatibility
- measurement uniqueness
- biological sample resolution
- endpoint availability
- required factor levels
- paired completeness
- crossed/nested consistency
- rank deficiency
- factor confounding
- insufficient repeated measurements
- missing reference condition
- acceptance criterion computability

Output:

```text
design_validation.json
design_summary.md
factor_balance.tsv
confounding_matrix.tsv
criterion_computability.tsv
recommendations.json
```

Separate:

- blocking errors
- warnings
- informational notes
- recommendations

---

## 21. `RUN_ASSAY_STUDY` Workflow

```groovy
workflow RUN_ASSAY_STUDY {
    VALIDATE_STUDY_SPEC(params.study_spec)
    VERIFY_LOCKED_MODEL(...)
    VALIDATE_STUDY_DESIGN(...)
    BUILD_ENDPOINT_TABLE(...)

    if (params.study_type == 'precision_reproducibility') {
        PRECISION_REPRODUCIBILITY_ANALYSIS(...)
    } else if (params.study_type == 'input_degradation_limit') {
        INPUT_DEGRADATION_LIMIT_ANALYSIS(...)
    } else if (params.study_type == 'paired_bridging') {
        PAIRED_BRIDGING_ANALYSIS(...)
    } else if (params.study_type == 'robustness_interference') {
        ROBUSTNESS_INTERFERENCE_ANALYSIS(...)
    } else {
        error "Unsupported analytical study type"
    }

    EVALUATE_ACCEPTANCE_CRITERIA(...)
    BUILD_VALIDATION_BUNDLE(...)
    GENERATE_VALIDATION_DECISION_SUMMARY(...)
    EVALUATE_NEXT_ACTION_RULES(...)
    RENDER_VALIDATION_REPORT(...)
}
```

Never launch nested Nextflow from inside this workflow. Reuse prediction subworkflows called by `PREDICT_WITH_MODEL`.

---

## 22. Analytical Study Templates

### 22.1 Precision and reproducibility

Supported designs:

- within-run repeatability
- between-run precision
- operator, lot, instrument, day, and site factors
- crossed and constrained nested designs

Continuous metrics:

- mean, SD, CV
- repeatability SD
- reproducibility SD
- variance components
- ICC
- concordance correlation when appropriate
- within-sample range
- bootstrap confidence intervals

Categorical metrics:

- percent agreement
- positive and negative agreement where meaningful
- Cohen’s kappa when appropriate
- per-sample call stability
- discordance table

Always report threshold proximity and disagreements near the decision boundary.

### 22.2 Input and degradation limit

- ordered input or quality levels
- paired reference comparison where available
- trend and change-point exploration
- score and call stability
- QC deterioration
- all-level and consecutive-level rules

The system may report the lowest tested level meeting declared criteria. It must not automatically call it a clinical LoD.

### 22.3 Paired bridging

Use for:

- pipeline version A versus B
- reagent or library method changes
- instrument changes
- reference or annotation updates

Analyses:

- paired bias
- confidence intervals
- Bland–Altman
- Deming or appropriate regression when justified
- categorical agreement and discordance
- optional TOST with prespecified margin
- subgroup and threshold-adjacent review

Correlation alone cannot pass equivalence.

### 22.4 Robustness and interference

Use challenge/reference pairs where possible.

Potential challenges:

- low tumor content
- normal-tissue admixture
- blood or hemoglobin
- genomic DNA
- degradation
- handling deviations
- sequencing-depth reduction
- processing timing

Report challenge effects and call changes. Do not generate unsupported biological-specificity claims.

---

## 23. Acceptance-Criteria Engine

Supported operators:

```text
gt
gte
lt
lte
between
absolute_lte
all_levels
consecutive_levels
categorical_equals
```

Criterion result:

```text
NOT_EVALUATED
PASS
FAIL
INDETERMINATE
NOT_APPLICABLE
```

Rules:

- Criteria must be frozen before Study execution.
- Missing or non-computable metrics return `INDETERMINATE` or `NOT_APPLICABLE`, never a silent pass.
- Preserve observed values, uncertainty, population, endpoint, threshold, and rationale.
- Study-level status must not conceal individual failures.
- Exploratory Development Experiments may use learning questions instead of pass/fail criteria.

---

## 24. Validation Bundle

```text
validation_bundle/
├── manifest.json
├── study_spec.yaml
├── model_manifest.json
├── design/
│   ├── study_assignments.tsv
│   ├── design_validation.json
│   ├── factor_balance.tsv
│   └── confounding_matrix.tsv
├── endpoints/
│   ├── endpoint_table.parquet
│   ├── endpoint_table.tsv.gz
│   └── excluded_measurements.tsv
├── metrics/
│   ├── precision_metrics.json
│   ├── variance_components.json
│   ├── agreement_metrics.json
│   ├── threshold_stability.json
│   └── acceptance_results.json
├── figures/
├── decision/
│   ├── decision_summary.json
│   ├── decision_summary.md
│   ├── recommendations.json
│   └── unresolved_questions.json
├── provenance/
│   ├── input_checksums.tsv
│   ├── software_versions.yml
│   ├── container_digests.tsv
│   ├── parameters.json
│   └── nextflow_metadata/
└── report/
    ├── validation_report.html
    └── validation_report.pdf
```

The generic result renderer must support Expression Bundles, Result Bundles, Development Evidence Bundles, and Validation Bundles through manifests.

---

## 25. GUI Requirements

### 25.1 Navigation

Recommended top-level navigation:

```text
Projects
Assay Development
Datasets
Analyses
Experiments
Models
Validation Studies
Runs
```

### 25.2 Assay project dashboard

Show:

- lifecycle stage rail
- current question
- readiness card
- known evidence
- missing information
- blockers and warnings
- recommended next action
- alternatives
- recent decisions
- open experiments/studies
- one-click “Create recommended action”

### 25.3 Recommended action card

Must visually separate:

- blocker
- strongly recommended
- recommended
- optional
- not recommended

Each card includes `Why`, `Evidence`, `Resolves`, `Limitations`, and `Scientist decision required`.

### 25.4 Question-first wizard

Do not expose an unrestricted statistics playground.

The user should be able to begin with “What are you trying to learn?” and receive a constrained design template.

### 25.5 Experiment review page

Before execution show:

- question and decision to inform
- planned design
- sample and measurement counts
- factor balance
- paired completeness
- detected confounding
- endpoints
- exploratory questions or criteria
- missing information
- generated ExperimentSpec
- wet-lab execution export

### 25.6 Results page

Lead with:

```text
Question
Finding
Evidence
Limitations
Declared criteria or learning questions
Recommended next action
Alternative actions
Scientist decision
```

Detailed metrics and plots follow.

### 25.7 Expert mode

Expert mode may allow direct access to analysis and study configuration. It must not bypass schema checks, provenance, design validation, model lock, or immutability.

---

## 26. API Expansion

### 26.1 Assay development projects

```text
POST   /assay-projects
GET    /assay-projects/{id}
PATCH  /assay-projects/{id}
GET    /assay-projects/{id}/readiness
GET    /assay-projects/{id}/recommendations
POST   /assay-projects/{id}/recompute-guidance
POST   /assay-projects/{id}/stage-decisions
GET    /assay-projects/{id}/timeline
```

### 26.2 Questions and decisions

```text
GET    /scientific-questions/catalog
POST   /assay-projects/{id}/questions
PATCH  /questions/{id}
POST   /recommendations/{id}/accept
POST   /recommendations/{id}/reject
POST   /recommendations/{id}/modify
POST   /decisions
```

### 26.3 Development experiments

```text
POST   /experiments
GET    /experiments/{id}
PATCH  /experiments/{id}
POST   /experiments/{id}/validate-design
POST   /experiments/{id}/lock-execution-revision
POST   /experiments/{id}/run
POST   /experiments/{id}/clone
GET    /experiments/{id}/results
GET    /experiments/{id}/recommendations
```

### 26.4 Models and studies

Retain model lifecycle and Study endpoints from the original amendment.

### 26.5 API rules

- Use Pydantic schemas.
- Validate server-side regardless of frontend checks.
- Return structured errors, warnings, and recommendations separately.
- Do not embed scientific calculations in API handlers.
- Store immutable artifact references rather than large endpoint tables in PostgreSQL.
- Write audit events for lock, execution, recommendation resolution, and stage decisions.

---

## 27. Repository Additions

Suggested additions:

```text
apps/api/app/
├── assay_projects/
├── questions/
├── recommendations/
├── decisions/
├── experiments/
├── studies/
└── model_registry/

apps/web/src/features/
├── assay-projects/
├── guided-workflow/
├── question-wizard/
├── experiment-designer/
├── readiness/
├── recommendations/
├── decisions/
├── experiments/
├── model-registry/
└── validation-studies/

contracts/
├── assay_project/
├── guidance/
│   ├── readiness.schema.json
│   ├── recommendation.schema.json
│   └── decision_summary.schema.json
├── experiment/
│   ├── experiment_spec.schema.json
│   ├── experiment_manifest.schema.json
│   └── assignment.schema.json
├── model/
│   └── model_manifest.schema.json
└── validation/
    ├── study_spec.schema.json
    └── validation_manifest.schema.json

workflows/
├── assay_experiment.nf
├── assay_study.nf
└── subworkflows/
    ├── experiment/
    ├── validation/
    └── prediction/

modules/local/
├── guidance/
├── experiment_design/
├── experiment_analysis/
├── validation_design/
├── validation_analysis/
├── criteria/
└── reporting/

packages/
├── transcriptforge_guidance/
├── transcriptforge_experiment_design/
├── transcriptforge_assay_stats/
└── transcriptforge_contracts/

docs/
├── guided_assay_development.md
├── question_catalog.md
├── human_scientific_judgment.md
├── development_vs_validation.md
└── study_templates/
```

---

## 28. Scientific Implementation Boundaries

### 28.1 TranscriptForge decides programmatically

- whether required inputs are present
- whether schemas validate
- whether a design is identifiable
- whether factors are confounded
- whether a model is locked and intact
- which requested calculation to execute
- observed metrics and uncertainty
- whether declared criteria are met
- whether outputs are reproducible
- whether assets changed
- which deterministic recommendation rules fired

### 28.2 TranscriptForge may recommend

- the next supported question to address
- a paired, crossed, or nested template
- blocked randomization
- removal of a non-estimable factor
- additional replication
- a targeted follow-up experiment
- useful sensitivity analyses
- threshold-adjacent enrichment
- whether evidence appears insufficient for the next milestone

Recommendations must show evidence and never silently modify locked configuration.

### 28.3 The assay scientist decides

- proposed intended use
- specimen type and realistic conditions
- clinically or scientifically important failure modes
- primary endpoint
- acceptance thresholds
- equivalence margins
- meaningful score changes
- whether a minimum-input conclusion is justified
- whether to advance, repeat, redesign, lock, or stop
- whether additional studies are required

Represent these decisions as versioned configuration and DecisionRecords.

---

## 29. Statistical Software Design

Use mature libraries behind stable package APIs.

### 29.1 R functions

Potential functions:

```text
validate_design_matrix()
fit_mixed_effects_model()
estimate_variance_components()
calculate_icc()
calculate_agreement()
paired_condition_analysis()
ordered_level_analysis()
bridging_analysis()
robustness_analysis()
render_assay_report()
```

Potential packages may include `lme4`, `nlme`, `emmeans`, `performance`, `irr`, `DescTools`, `mcr`, `TOSTER`, `ggplot2`, and `quarto`, subject to method review and pinned versions.

### 29.2 Python functions

Potential functions:

```text
validate_experiment_spec()
validate_study_spec()
build_endpoint_table()
compute_factor_balance()
detect_confounding()
evaluate_acceptance_criteria()
evaluate_guidance_rules()
build_decision_summary()
build_development_manifest()
build_validation_manifest()
verify_model_integrity()
```

### 29.3 Function requirements

- pure functions where feasible
- typed inputs and outputs
- deterministic fixtures
- explicit missing-data behavior
- no silent fallback between statistical methods
- structured warnings
- method and package versions captured
- edge cases covered by tests

---

## 30. Audit and Provenance Events

Record events for:

```text
ASSAY_PROJECT_CREATED
STAGE_RECOMMENDED
STAGE_DECISION_RECORDED
QUESTION_CREATED
QUESTION_RESOLVED
READINESS_RECOMPUTED
RECOMMENDATION_CREATED
RECOMMENDATION_ACCEPTED
RECOMMENDATION_REJECTED
RECOMMENDATION_MODIFIED
EXPERIMENT_CREATED
EXPERIMENT_DESIGN_VALIDATED
EXPERIMENT_REVISION_LOCKED
EXPERIMENT_RUN_STARTED
EXPERIMENT_RUN_COMPLETED
DECISION_SUMMARY_CREATED
MODEL_REVIEWED
MODEL_LOCKED
MODEL_RETIRED
STUDY_CREATED
STUDY_DESIGN_VALIDATED
STUDY_LOCKED
STUDY_RUN_STARTED
STUDY_RUN_COMPLETED
```

Every event should include actor, timestamp, object IDs, revision, and relevant hashes.

---

## 31. Demo Strategy

Ship one coherent seeded assay-development story rather than disconnected demos.

### 31.1 Demo narrative

A synthetic FFPE RNA classifier-development project should include:

- biological samples with outcome labels
- RNA input and DV200
- operators, lots, runs, and instruments
- technical replicates
- a deliberately confounded initial subset
- simulated biological signal
- degradation and low-input effects
- borderline samples near a classifier threshold
- a comparator and candidate pipeline version
- a challenge condition

### 31.2 Guided demo path

```text
1. Open seeded Assay Development Project.
2. Dashboard identifies unresolved batch confounding.
3. Accept recommendation to create a balanced feasibility/optimization experiment.
4. Review generated design and correct one deliberate assignment problem.
5. Run RUN_ASSAY_EXPERIMENT.
6. Review decision summary and accept recommendation to proceed to classifier development.
7. Run guided classifier development.
8. Review readiness and lock an eligible candidate.
9. Accept recommendation to create a precision/reproducibility study.
10. Run RUN_ASSAY_STUDY.
11. Review acceptance results and threshold stability.
12. Create a targeted follow-up from the next-action recommendation.
13. Download Development Evidence and Validation Bundles.
```

### 31.3 Demo language

Clearly label all data and criteria as synthetic portfolio demonstrations.

---

## 32. Testing Expansion

### 32.1 Schema tests

- AssayProject
- readiness result
- recommendation
- DecisionRecord
- ExperimentSpec
- experiment assignment
- development manifest
- ModelManifest
- StudySpec
- validation manifest

### 32.2 Guidance-rule tests

For every rule:

- positive trigger fixture
- negative fixture
- boundary fixture
- evidence references
- stable recommendation output
- no duplicate active recommendation
- supersession behavior

### 32.3 Experiment-design tests

- balanced paired design
- missing pair
- factor confounding
- rank deficiency
- unbalanced but estimable design
- no reference condition
- missing replicates
- retrospective mapping warning

### 32.4 Scientific tests

- known paired difference
- known variance components
- input-level trend
- known systematic bridging bias
- threshold-adjacent discordance
- challenge/reference effect
- deterministic bootstrap fixture

### 32.5 Model-lock tests

- valid lock
- missing asset
- failed inference fixture
- checksum change
- immutable locked object
- clone to new candidate

### 32.6 Nextflow tests

For `RUN_ASSAY_EXPERIMENT`:

- minimal successful feasibility experiment
- invalid ExperimentSpec fails before analysis
- confounded blocked design fails
- deterministic selected outputs
- Development Evidence Bundle validates

For `RUN_ASSAY_STUDY`:

- minimal successful precision study
- unlocked model fails
- checksum mismatch fails
- invalid StudySpec fails before endpoint generation
- deterministic selected outputs
- Validation Bundle validates

### 32.7 API and frontend tests

- project dashboard
- stage rail
- readiness display
- question selection
- experiment wizard
- factor mapping
- errors versus warnings
- recommendation acceptance/rejection/modification
- DecisionRecord creation
- read-only locked revision
- result decision summary
- one-click follow-up creation

### 32.8 End-to-end tests

Retain the original PCA end-to-end path.

Add guided paths:

#### Guided development experiment

1. Open seeded assay project.
2. View readiness blockers.
3. Accept a recommendation.
4. Create experiment from template.
5. Fix deliberate confounding error.
6. Lock execution revision.
7. Run experiment.
8. View decision summary.
9. Accept next-action recommendation.

#### Locked validation study

1. Open eligible classifier candidate.
2. Lock model.
3. Create precision study from recommendation.
4. Validate and lock design.
5. Run study.
6. View metrics, criteria, and threshold stability.
7. Download Validation Bundle.

---

## 33. Implementation Sequence

Do not build every study type or a complex AI assistant at once.

### Amendment Phase G0: Contracts and guided-project scaffolding

Tasks:

- Add this amendment to `docs/`.
- Add AssayProject, Question, Recommendation, DecisionRecord, ExperimentSpec, ModelManifest, and StudySpec schemas.
- Add lifecycle stage and readiness contracts.
- Add feature flags.
- Add static question catalog.

Acceptance:

- Schemas validate examples.
- Existing workflows and tests remain unchanged.
- Guided features do not appear as functional before they work.

### Amendment Phase G1: Guided dashboard and deterministic readiness

Tasks:

- Add AssayDevelopmentProject entity and API.
- Add stage rail and dashboard.
- Implement a small deterministic readiness engine.
- Implement Recommendation and DecisionRecord lifecycle.
- Add question-first wizard shell.

Acceptance:

- Seeded project displays known, missing, blocker, recommended, alternative, and not-recommended actions.
- Every recommendation shows the rule and evidence.
- User can accept, reject, or modify it.

### Amendment Phase G2: First pre-lock experiment vertical slice

Implement `TECHNICAL_FEASIBILITY` or `INPUT_DEGRADATION_EXPLORATION` end to end.

Tasks:

- Experiment domain and API.
- ExperimentSpec and assignments.
- Design validator.
- `RUN_ASSAY_EXPERIMENT`.
- Development Evidence Bundle.
- Decision summary.
- Next-action recommendation.
- Wet-lab execution export.

Acceptance:

- A user can begin with a plain-language question and complete the entire guided loop.
- The result creates a defensible next-action recommendation.
- The user can create the follow-up action in one click.

### Amendment Phase G3: Guided integration with existing analyses

Tasks:

- Route questions to PCA, DE, deconvolution, signature, and classifier workflows.
- Generate GuidanceResult artifacts after analyses.
- Recompute readiness after completion.

Acceptance:

- Existing scientific workflows remain the source of calculations.
- Guided summaries correctly reference Result Bundle artifacts.

### Amendment Phase G4: Locked model lifecycle

Tasks:

- Extend ModelRecord.
- Add review, lock, clone, retire, and integrity operations.
- Harden `PREDICT_WITH_MODEL`.
- Add lock-readiness rules.

Acceptance:

- Candidate can be locked only when required checks pass.
- Prediction is deterministic.
- Asset changes cause integrity failure.

### Amendment Phase G5: Precision/reproducibility validation vertical slice

Tasks:

- Study domain and API.
- StudySpec and design validator.
- `RUN_ASSAY_STUDY`.
- Precision metrics, variance components, ICC, agreement, and threshold analysis.
- Criteria engine.
- Validation Bundle and report.
- Guided next action.

Acceptance:

- User can create the study from a dashboard recommendation.
- A locked model is never retrained.
- Criteria return pass/fail/indeterminate/not applicable.

### Amendment Phase G6: Additional experiment and study templates

Add in this order:

1. Paired condition comparison.
2. Input/degradation limit.
3. Paired bridging.
4. Robustness/interference.
5. Multifactor optimization.

Each template requires scientific, schema, design, UI, and end-to-end tests.

### Amendment Phase G7: Portfolio polish and cloud execution

- one-command seeded demo
- architecture diagrams
- guided tutorial
- local and AWS Batch runs
- cost/runtime notes
- screenshots or short walkthrough
- clear explanation of human scientific judgment

---

## 34. Immediate Codex Milestone

The first implementation request from this amendment should be:

> Extend the existing TranscriptForge architecture with a stage-aware Assay Development Project and one guided pre-lock RNA feasibility experiment. Preserve all existing workflows. Add the project lifecycle, deterministic readiness checks, question catalog, Recommendation and DecisionRecord entities, a question-first experiment wizard, ExperimentSpec and assignment schemas, a design validator, `RUN_ASSAY_EXPERIMENT`, a Development Evidence Bundle, a decision summary, and a rule-based next-action recommendation. Use a seeded synthetic FFPE RNA input/degradation example. Do not implement all experiment types, model locking, or post-lock validation until this guided vertical slice passes all tests.

Definition of done:

1. Start TranscriptForge using the existing development command.
2. Open a seeded Assay Development Project.
3. See the current stage, known evidence, missing information, blockers, and recommended next action.
4. Select the question “Can lower RNA input or poorer RNA quality destabilize the expression endpoint?”
5. Create the recommended experiment.
6. Map samples, measurements, input levels, DV200, run, and operator.
7. Observe a deliberate confounding error.
8. Correct the assignment or approve a supported redesign.
9. Lock the execution revision.
10. Run `RUN_ASSAY_EXPERIMENT` through Nextflow.
11. View the question, finding, evidence, limitations, and condition-level results.
12. View a rule-based recommended next action and alternatives.
13. Accept the recommendation and create a draft follow-up action.
14. Download the Development Evidence Bundle, report, ExperimentSpec, assignments, logs, trace, timeline, DAG, versions, and checksums.
15. Confirm that modifying the locked execution revision causes an integrity error or requires cloning.

---

## 35. Expanded Definition of Done

TranscriptForge is portfolio-ready for guided assay development when:

- The default Assay Development Project view tells the user where they are and what to do next.
- Plain-language questions route to constrained experiment or analysis templates.
- Readiness checks identify missing information, blockers, and warnings.
- The design assistant catches confounding and non-identifiable designs.
- At least one pre-lock experiment works end to end.
- Every experiment result includes a decision summary and next-action recommendation.
- Recommendations display evidence, assumptions, limitations, and alternatives.
- Users must accept, reject, or modify material recommendations.
- Existing PCA, DE, signature, deconvolution, and classifier workflows can be launched from guided questions.
- Classifier candidates can be promoted to immutable locked models.
- At least one precision/reproducibility study works end to end.
- At least one additional validation template is implemented after precision.
- Development Evidence and Validation Bundles validate against schemas.
- All critical inputs, decisions, rationales, versions, and checksums are traceable.
- Local and one cloud profile execute the same specs with profile changes only.
- The demo clearly separates software capability from evidence about a real assay.
- The product makes no unsupported clinical or regulatory claims.

---

## 36. Portfolio Narrative

Use this concise description:

> TranscriptForge is a Nextflow-based guided RNA assay-development workbench. It standardizes RNA-seq and microarray data, supports exploratory transcriptomics and leakage-resistant classifier development, and then helps a scientist decide what to do next through stage-aware readiness checks, question-first experiment design, deterministic design validation, decision summaries, and transparent next-action recommendations. It separates iterative pre-lock development experiments from immutable model locking and post-lock analytical validation, producing traceable Development Evidence and Validation Bundles without making unsupported clinical claims.

Key interview message:

```text
I did not build another dashboard that ends with plots.
I built a guided scientific workflow that helps define the next question,
construct a defensible experiment, analyze the result, preserve the decision,
and move from exploratory RNA biology toward a locked and testable analytical product.
```

---

## 37. Final Guardrail for Codex

When implementation details conflict, preserve these priorities in order:

1. The user must always understand where they are and what to do next.
2. Scientific correctness and transparent limitations.
3. Question-first experiment design rather than method-first menus.
4. Deterministic, evidence-linked recommendations with human approval.
5. Separation of pre-lock development from post-lock validation.
6. Immutable data, model, experiment, and study revisions.
7. Reproducible Nextflow execution and provenance.
8. Reuse of existing TranscriptForge architecture and scientific modules.
9. A narrow, polished guided vertical slice before broad template support.
10. Research-use language with no unsupported regulatory or clinical claims.

Do not rewrite the existing application around this feature. Add the guided assay-development layer cleanly around the existing `Project`, `Dataset`, `PreparedDataset`, `Analysis`, `Run`, `Artifact`, and `ModelRecord` architecture.
