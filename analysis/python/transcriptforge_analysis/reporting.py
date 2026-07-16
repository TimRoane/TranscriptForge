"""Reusable Quarto report sources for exploratory analyses."""

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path


def write_dimension_reduction_report(
    output_dir: Path,
    *,
    title: str,
    analysis_id: str,
    assay: str,
    summary: Mapping[str, str | int | float],
    images: Sequence[tuple[str, str]],
    notes: Sequence[str] = (),
) -> None:
    """Write a portable Quarto source plus an HTML fallback for direct library use."""
    summary_rows = "\n".join(
        f"| {_markdown(label)} | {_markdown(str(value))} |" for label, value in summary.items()
    )
    image_blocks = "\n\n".join(
        f"## {_markdown(label)}\n\n![{_markdown(label)}]({path})" for label, path in images
    )
    note_blocks = "\n".join(f"- {_markdown(note)}" for note in notes)
    qmd = (
        "---\n"
        f"title: {json.dumps(title)}\n"
        "format:\n"
        "  html:\n"
        "    toc: true\n"
        "    embed-resources: true\n"
        "    theme: cosmo\n"
        "execute:\n"
        "  enabled: false\n"
        "---\n\n"
        f"Analysis `{_markdown(analysis_id)}` used the **{_markdown(assay)}** assay.\n\n"
        "## Analysis summary\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"{summary_rows}\n\n"
        f"{image_blocks}\n\n"
        + (f"## Interpretation notes\n\n{note_blocks}\n\n" if note_blocks else "")
        + "::: {.callout-important}\n"
        "## Research use only\n\n"
        "These exploratory results are not clinically validated. Interpret them with the "
        "study design, sample quality control, and relevant biological context.\n"
        ":::\n"
    )
    (output_dir / "report.qmd").write_text(qmd, encoding="utf-8")

    rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in summary.items()
    )
    figures = "".join(
        f"<h2>{html.escape(label)}</h2><img src='{html.escape(path)}' "
        f"alt='{html.escape(label)}' style='max-width:100%'>"
        for label, path in images
    )
    note_list = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
    (output_dir / "report.html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font:16px system-ui;max-width:960px;margin:3rem auto;color:#17323a}"
        "table{border-collapse:collapse}td,th{padding:.5rem 1rem;border:1px solid #ccd}"
        ".notice{padding:1rem;background:#eef6f8;border-radius:8px}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p>Analysis <code>{html.escape(analysis_id)}</code> "
        f"used the <strong>{html.escape(assay)}</strong> assay.</p>"
        f"<h2>Analysis summary</h2><table><tbody>{rows}</tbody></table>{figures}"
        + (f"<h2>Interpretation notes</h2><ul>{note_list}</ul>" if note_list else "")
        + "<p class='notice'><strong>Research use only.</strong> These exploratory results "
        "are not clinically validated. Interpret them with study design, sample quality "
        "control, and relevant biological context.</p></body></html>\n",
        encoding="utf-8",
    )


def _markdown(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`")
