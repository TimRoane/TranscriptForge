# Guided assay development

TranscriptForge is extending its reproducible transcriptomics workspace with a question-first assay-development lifecycle. The authoritative product and implementation requirements are in [the revised amendment](../TranscriptForge_Assay_Development_Validation_Amendment_REVISED.md).

The guided workspace separates two scientific modes:

- Development Experiments are pre-lock, exploratory or optimization work. Results may motivate changes, but TranscriptForge records those changes as explicit scientist decisions.
- Analytical Studies are post-lock, prespecified evaluations of an immutable model or signature. Changes require a cloned revision and cannot silently retrain the endpoint.

## Lifecycle and readiness

Projects progress through `DEFINE`, `FEASIBILITY`, `EXPLORE`, `OPTIMIZE`, `DEVELOP`, `LOCK`, `VALIDATE`, and `REPORT`, with `ON_HOLD` and `COMPLETED` as explicit states. Stage changes are recommendations until a scientist approves them.

Readiness is deterministic and transparent. Every finding identifies the rule, facts, conclusion, severity, suggested action, assumptions, and documentation. Version 1 does not use a hidden readiness score.

## Contract boundary

Versioned schemas live under `contracts/` for assay projects, scientific questions, readiness, recommendations, DecisionRecords, ExperimentSpecs, experiment assignments, ModelManifests, and StudySpecs. Valid examples live under `contracts/examples/`. The static question-routing catalog is `apps/api/transcriptforge_api/resources/scientific_question_catalog.json`.

The guided workspace and both new execution surfaces are independently feature-flagged. Their
vertical slices now satisfy schema, API, workflow, scientific, and end-to-end acceptance, so the
local single-user profile enables them by default; an operator can still disable each surface
independently. Existing workflows are unaffected.

## Guided portfolio tutorial

Start the local stack, apply migrations, and create the question-first teaching project:

```bash
make dev
make migrate
make seed-assay-development
```

Open the `assay_url` printed by the seeder. The initial input/degradation draft is deliberately
blocked because input level is aligned with run. Review the exact rule and input facts, distribute
levels across runs in the assignment table, save, and confirm that the design becomes valid. Locking
freezes the ExperimentSpec and assignments; it still does not launch computation. The next button
runs that exact revision, and cancellation remains available while it is queued or running.

The supported path is intentionally stage-aware:

1. In `FEASIBILITY`, summarize explicitly tested technical usability or explore input/degradation
   behavior without inferring a clinical specimen requirement or calling the lowest stable tested
   level a clinical LoD.
2. In `OPTIMIZE`, compare paired conditions across complementary endpoints or fit a constrained
   two-to-three-factor model. Sparse or rank-deficient requests are blocked.
3. In `DEVELOP` and `LOCK`, build, review, deterministically test, and explicitly lock a candidate
   classifier. Locking freezes features, preprocessing, coefficients, calibration, and threshold.
4. In `VALIDATE`, select the matching question and create precision/reproducibility,
   input/degradation-limit, paired-bridging, or robustness/interference evidence. Every study maps an
   immutable validation bundle, a locked model, assignments, and prespecified criteria.
5. Review each criterion and limitation. Accepting or modifying a recommendation creates a visible
   draft or DecisionRecord; it never silently launches the next action.

To execute or re-verify all seven deterministic Development Experiment and Analytical Study templates
through real Nextflow entry points with the repository virtual environment, run:

```bash
make assay-validation-demo
```

The command is cache-aware and writes checksummed evidence plus elapsed times to
`.transcriptforge-demo/assay_development/portfolio/portfolio_execution_summary.json`. It covers
technical feasibility, paired-condition comparison, constrained multifactor optimization, precision/reproducibility,
input/degradation limit, paired bridging, and robustness/interference.

## Interpretation boundaries by template

| Template | What the software establishes | What remains a scientist decision |
|---|---|---|
| Technical feasibility | Explicit technical success, expression suitability, and descriptive failure patterns | Whether feasibility supports further work; no clinical specimen requirement is inferred |
| Input/degradation exploration | Ordered paired behavior and technical deterioration | Candidate condition and need for prospective confirmation |
| Paired condition comparison | Bias, intervals, concordance, failures, and quality interaction | Whether combined endpoints favor a confirmation condition |
| Multifactor optimization | Estimable frozen effects/interactions and descriptive variance | Which supported cells merit confirmation |
| Precision/reproducibility | Frozen score/call precision against declared criteria | Whether evidence is sufficient for the intended research use |
| Input/degradation limit | Lowest tested consecutive level meeting declared criteria | Whether further LoD-oriented work is justified |
| Paired bridging | Bias/agreement/TOST evidence; correlation is descriptive | Whether the prespecified margin and evidence support a bridge |
| Robustness/interference | Tested technical challenge effects and call/QC changes | Risk acceptance; no unsupported biological-specificity claim |

## Human scientific judgment

TranscriptForge may validate inputs and designs, calculate declared metrics, evaluate frozen criteria, and recommend supported next actions. It never silently chooses an intended use, endpoint, acceptance threshold, equivalence margin, model lock, stage transition, or advance/stop decision. These remain versioned scientist decisions.
