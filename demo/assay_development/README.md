# Synthetic FFPE assay-development demonstration

This deterministic, entirely synthetic study contains six paired biological profiles measured at
100, 50, and 25 ng. Lower-input measurements receive progressively more simulated feature noise and
dropout. No row represents a person, clinical specimen, or observed biological effect.

`make seed-assay-development` generates the compact matrix, prepares it through the real API/worker/
Nextflow path, creates a guided feasibility workspace, selects the input/degradation question, and
adds an intentionally invalid experiment where each input level is perfectly confounded with run.
The GUI exposes the blocker and allows the reviewer to repair run assignments using the balanced
run metadata retained in the Expression Bundle. The seeder does not lock or run the experiment.
