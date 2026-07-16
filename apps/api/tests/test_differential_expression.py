"""Method-neutral differential-expression result parsing tests."""

from transcriptforge_api.services.differential_expression import parse_results


def test_count_model_log_cpm_abundance_is_labeled_without_inventing_standard_error() -> None:
    payload = (
        b"feature_id\tgene_symbol\taverage_log_cpm\tlog2_fold_change\tstandard_error\t"
        b"statistic\tp_value\tadjusted_p_value\tcontrast\tmethod\tsignificant\n"
        b"gene_1\tABC1\t7.5\t1.25\t\t12.4\t0.0001\t0.002\ttreated versus control\t"
        b"edgeR QL\tTRUE\n"
    )

    rows, label = parse_results(payload)

    assert label == "Average log2 CPM"
    assert rows[0].base_expression == 7.5
    assert rows[0].standard_error is None
    assert rows[0].method == "edgeR QL"
