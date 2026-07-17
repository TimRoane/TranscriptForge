"""Microarray Expression Bundle assembly tests."""

import json
import tarfile
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.microarray_bundle_cli import build_microarray_bundle

ROOT = Path(__file__).parents[3]


def test_rma_outputs_form_probe_and_gene_expression_bundle(tmp_path: Path) -> None:
    r_output = tmp_path / "rma"
    plots = r_output / "plots"
    plots.mkdir(parents=True)
    ingestion = {
        "schema_version": "1.0.0",
        "dataset_id": "dataset-microarray-1",
        "organism": "Homo sapiens",
        "source_kind": "affymetrix_cel",
        "platform": {
            "platform_id": "affymetrix_hugene_1_0_st_v1",
            "definition_sha256": "a" * 64,
            "adapter_version": "1.0.0",
            "vendor": "Affymetrix",
            "array_design": "Human Gene 1.0 ST Array",
            "detected_chip_type": "HuGene-1_0-st-v1",
            "cel_format": "calvin",
            "normalization": {
                "engine": "oligo",
                "method": "rma",
                "target": "probeset",
                "pd_info_package": "pd.hugene.1.0.st.v1",
            },
            "annotation": {
                "package": "hugene10sttranscriptcluster.db",
                "probe_key": "PROBEID",
                "gene_id_field": "ENSEMBL",
                "gene_symbol_field": "SYMBOL",
                "confidence": "explicit_platform_adapter",
            },
        },
        "aggregation_method": "highest_mad",
        "sample_metadata": {
            "original_name": "samples.tsv",
            "sha256": "b" * 64,
        },
        "samples": [
            {
                "sample_id": sample,
                "cel_file": {"original_name": f"{sample}.CEL", "sha256": digest * 64},
            }
            for sample, digest in (("control_1", "c"), ("control_2", "d"), ("treated_1", "e"))
        ],
    }
    ingestion_path = tmp_path / "ingestion.json"
    ingestion_path.write_text(json.dumps(ingestion), encoding="utf-8")
    metadata = tmp_path / "samples.tsv"
    metadata.write_text(
        "sample_id\tcel_file\tcondition\n"
        "control_1\tcontrol_1.CEL\tcontrol\n"
        "control_2\tcontrol_2.CEL\tcontrol\n"
        "treated_1\ttreated_1.CEL\ttreated\n",
        encoding="utf-8",
    )
    gene_expression = r_output / "gene_expression.tsv"
    gene_expression.write_text(
        "feature_id\tcontrol_1\tcontrol_2\ttreated_1\n"
        "ENSG00000000001\t5.1\t5.2\t7.4\n"
        "ENSG00000000002\t8.0\t8.1\t7.9\n",
        encoding="utf-8",
    )
    probe_expression = r_output / "probe_expression.tsv"
    probe_expression.write_text(
        "probe_id\tcontrol_1\tcontrol_2\ttreated_1\n"
        "1001\t5.1\t5.2\t7.4\n1002\t5.0\t5.2\t7.1\n1003\t8.0\t8.1\t7.9\n",
        encoding="utf-8",
    )
    feature_metadata = r_output / "gene_feature_metadata.tsv"
    feature_metadata.write_text(
        "feature_id\tensembl_gene_id\tgene_symbol\tentrez_id\tgene_name\tgene_biotype\t"
        "chromosome\tstart\tend\tmapping_status\toriginal_feature_id\tselected_probe_id\t"
        "aggregation_method\n"
        "ENSG00000000001\tENSG00000000001\tGENE1\t1\tGene one\t\t\t\t\tmapped\t"
        "1001;1002\t1001\thighest_mad\n"
        "ENSG00000000002\tENSG00000000002\tGENE2\t2\tGene two\t\t\t\t\tmapped\t"
        "1003\t1003\thighest_mad\n",
        encoding="utf-8",
    )
    probe_mapping = r_output / "probe_mapping.tsv"
    probe_mapping.write_text(
        "probe_id\ttranscript_cluster_id\tensembl_gene_id\tmapping_status\n"
        "1001\t2001\tENSG00000000001\tmapped\n",
        encoding="utf-8",
    )
    qc_metrics = r_output / "array_qc_metrics.tsv"
    qc_metrics.write_text(
        "sample_id\traw_log2_median\tstatus\treasons\ncontrol_1\t6.1\tPASS\t\n",
        encoding="utf-8",
    )
    sample_flags = r_output / "sample_flags.tsv"
    sample_flags.write_text("sample_id\tstatus\treasons\ncontrol_1\tPASS\t\n", encoding="utf-8")
    qc_summary = r_output / "array_qc_summary.json"
    qc_summary.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "status": "PASS",
                "sample_count": 3,
                "probe_count": 3,
                "gene_count": 2,
                "reviewed_sample_count": 0,
                "plots": ["plots/pca.svg"],
            }
        ),
        encoding="utf-8",
    )
    (r_output / "parameters.json").write_text("{}\n", encoding="utf-8")
    (r_output / "software_versions.yml").write_text("r: '4.6'\n", encoding="utf-8")
    (r_output / "session_info.txt").write_text("R fixture\n", encoding="utf-8")
    (plots / "pca.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>\n", encoding="utf-8")

    output = tmp_path / "output"
    build_microarray_bundle(
        ingestion_path,
        gene_expression,
        probe_expression,
        feature_metadata,
        probe_mapping,
        qc_metrics,
        sample_flags,
        qc_summary,
        r_output,
        metadata,
        output,
        "prepared-microarray-1",
        1,
    )

    manifest = json.loads((output / "bundle_manifest.json").read_text())
    schema = json.loads((ROOT / "schemas/expression_bundle.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert [assay["name"] for assay in manifest["assays"]] == [
        "log_expression",
        "probe_expression",
    ]
    assert manifest["microarray"]["aggregation_method"] == "highest_mad"
    assert manifest["microarray"]["annotation_confidence"] == "explicit_platform_adapter"
    assert manifest["qc"]["metrics"] == "qc/array_qc_metrics.tsv"
    assert "differential_expression" in manifest["assays"][0]["recommended_for"]
    assert not (output / "expression_bundle/qc/plots/library_sizes.svg").exists()
    summary = json.loads((output / "bundle_summary.json").read_text())
    assert summary["value_types_available"] == ["log_expression", "probe_expression"]
    assert summary["probe_count"] == 3
    with tarfile.open(output / "expression_bundle.tar.gz") as archive:
        names = set(archive.getnames())
    assert "expression_bundle/assays/log_expression.tsv.gz" in names
    assert "expression_bundle/assays/probe_expression.tsv.gz" in names
    assert "expression_bundle/mappings/probe_mapping.tsv" in names
