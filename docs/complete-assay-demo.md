# Complete synthetic assay-development demonstration

This demonstration is one coherent, fully synthetic assay story. It starts with paired
FFPE feasibility, crosses pre-lock exploration and optimization, develops and freezes a classifier,
and finishes with precision/reproducibility and robustness evidence. It is designed to show the
product and engineering lifecycle without making unsupported claims about a real assay.

## Create or resume the project

Start the local product, then run:

```bash
make seed-complete-assay-demo
```

The Make target uses the repository `.venv`, recreates the API and worker with the local `demo`
Nextflow profile, and assigns the host CPU count to deterministic classifier permutations. Override
that resource choice when needed:

```bash
make seed-complete-assay-demo DEMO_CLASSIFIER_CPUS=8
```

Every scientific action crosses the public API, durable worker, and real Nextflow entry point. The
seed does not insert database fixtures. It is safe to rerun: successful immutable resources are
reused, cancelled work is explicitly relaunched, and a failed run or stable-name configuration
conflict stops with an actionable error.

The generated source matrices and checkpoint live under `.transcriptforge-demo/complete_assay/`.
`complete_assay_seed_summary.json` contains resource IDs, statuses, input and artifact checksums,
elapsed time, and direct application URLs. Generation is checksum-stable and all five datasets use
the same ordered 2,000-feature Ensembl universe.

### Measured workstation execution

On the recorded 32-core development workstation, a clean database lineage completed through the
public API, worker, and Nextflow paths in **123.8 seconds**. An immediate cache-only rerun completed
in **0.40 seconds** and retained exactly 3 experiment records, 1 locked model, and 2 analytical
studies, demonstrating duplicate prevention. These measurements are evidence for this workstation,
not a universal runtime guarantee. The classifier used 32 deterministic permutation workers; use
`DEMO_CLASSIFIER_CPUS` to cap that concurrency on smaller machines.

## Synthetic evidence design

| Evidence set | Design | Purpose |
| --- | --- | --- |
| Feasibility | 6 specimens × 3 RNA inputs = 18 paired measurements | Demonstrate degradation-sensitive features and design-confounding repair |
| Optimization | 12 specimens × reference/candidate methods = 24 paired measurements | Compare bias, profile agreement, detection, and discordance before lock |
| Classifier development | 96 balanced, outcome-labeled specimens | Run grouped repeated nested CV, complete OOF prediction, and 100 deterministic permutations |
| Precision/reproducibility | 8 specimens × 4 crossed replicates = 32 measurements | Evaluate the unchanged locked score across operators, runs, lots, instruments, and days |
| Robustness | 12 specimens × reference/challenge aliquots = 24 paired measurements | Evaluate hemoglobin, freeze-thaw, and low-DV200 challenges without retraining |

The frozen truth file declares positive and negative classifier blocks, degradation-sensitive
features, a small candidate-method shift, technical run effects, borderline specimens, and 1,000
null features. The generator balances outcomes across technical factors and labels every artifact
as synthetic and research-use only.

## Guided review path

Open the `dashboard` URL in the seed summary and follow this sequence:

1. Review the lifecycle rail and the five prepared evidence datasets.
2. Open the confounded feasibility teaching draft. Its only design error is
   `DESIGN.INPUT_RUN_CONFOUNDED`; retrospective mapping remains a transparent warning.
3. Open the repaired child revision. Confirm clone lineage, crossed run assignments, immutable
   execution hashes, successful evidence, and explicit interpretation boundaries.
4. Review guided PCA and differential expression. Both link the question, exact Expression Bundle,
   run, and immutable GuidanceResult back to the assay project.
5. Review the paired library-method optimization experiment and its complementary endpoints.
6. Open the model-lifecycle card. Inspect grouped CV, OOF predictions, permutation evidence,
   model card, deterministic inference test, review rationale, lock hashes, and integrity result.
7. Open the two post-lock studies. Confirm that criteria are resolved against the frozen model and
   that both bundles state `model_retrained: false` and retain the scientist-decision boundary.
8. Finish on the assay dashboard at `REPORT`, where experiments, guided analyses, model lineage,
   studies, and recent stage decisions are visible together.

## Interpretation boundary

This demonstration establishes deterministic software behavior against known constructed effects.
It does not establish biological validity, diagnostic accuracy, clinical utility, a specimen
requirement, a limit of detection, or regulatory fitness. Scripted decisions exist to demonstrate
governance records; they are not substitutes for scientist or quality-system approval.

The precision study intentionally preserves one `NOT_APPLICABLE` QC-failure endpoint because the
locked inference output does not manufacture a missing QC event stream. Its score ICC and call
agreement criteria pass, but the aggregate remains `INDETERMINATE` and explicitly requires scientist
review. The robustness study has observable values for all three prespecified criteria and resolves
to `PASS`. This distinction is part of the demonstration's scientific-integrity boundary.
