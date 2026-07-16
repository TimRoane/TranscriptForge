"""Dependency-light, deterministic SVG exports for dimension reduction."""

import html
from pathlib import Path
from typing import Any

import numpy as np

_COLORS = ("#155e75", "#7c3aed", "#d97706", "#be123c", "#15803d", "#0369a1")


def write_scatter_svg(
    path: Path,
    *,
    title: str,
    sample_ids: list[str],
    coordinates: np.ndarray[Any, Any],
    axis_names: list[str],
    metadata: dict[str, dict[str, str]],
    axis_ratios: np.ndarray[Any, Any] | None = None,
) -> None:
    width, height, padding = 900, 590, 72
    x_values = coordinates[:, 0]
    y_values = coordinates[:, 1]
    x_min, x_max = _limits(x_values)
    y_min, y_max = _limits(y_values)
    def x(value: float) -> float:
        return padding + (float(value) - x_min) / (x_max - x_min) * (width - 2 * padding)

    def y(value: float) -> float:
        return height - padding - (float(value) - y_min) / (y_max - y_min) * (
            height - 2 * padding
        )
    columns = [key for key in metadata.get(sample_ids[0], {}) if key != "sample_id"]
    color_column = "treatment" if "treatment" in columns else (columns[0] if columns else None)
    categories = list(
        dict.fromkeys(
            metadata[sample].get(color_column, sample) if color_column else sample
            for sample in sample_ids
        )
    )
    colors = {value: _COLORS[index % len(_COLORS)] for index, value in enumerate(categories)}
    circles = []
    for row, sample_id in enumerate(sample_ids):
        category = metadata[sample_id].get(color_column, sample_id) if color_column else sample_id
        tooltip = (
            f"{sample_id}; {axis_names[0]}={float(x_values[row]):.3f}; "
            f"{axis_names[1]}={float(y_values[row]):.3f}"
        )
        circles.append(
            f"<circle cx='{x(x_values[row]):.2f}' cy='{y(y_values[row]):.2f}' r='6' "
            f"fill='{colors[category]}' stroke='white' stroke-width='1.5'>"
            f"<title>{html.escape(tooltip)}</title></circle>"
        )
    labels = list(axis_names[:2])
    if axis_ratios is not None:
        labels = [
            f"{axis} ({float(axis_ratios[index]) * 100:.1f}%)"
            for index, axis in enumerate(axis_names[:2])
        ]
    legend = "".join(
        f"<circle cx='{padding + index * 145}' cy='{height - 22}' r='5' fill='{colors[value]}'/>"
        f"<text x='{padding + 10 + index * 145}' y='{height - 18}' font-size='12'>"
        f"{html.escape(value)}</text>"
        for index, value in enumerate(categories[:6])
    )
    path.write_text(
        _svg_start(width, height, title)
        + f"<text x='{width / 2}' y='30' text-anchor='middle' font-size='22' "
        f"font-weight='700'>{html.escape(title)}</text>"
        f"<line x1='{padding}' y1='{height - padding}' x2='{width - padding}' "
        f"y2='{height - padding}' stroke='#94a3b8'/>"
        f"<line x1='{padding}' y1='{padding}' x2='{padding}' y2='{height - padding}' "
        f"stroke='#94a3b8'/>{''.join(circles)}"
        f"<text x='{width / 2}' y='{height - 42}' text-anchor='middle' font-size='14'>"
        f"{html.escape(labels[0])}</text>"
        f"<text x='20' y='{height / 2}' text-anchor='middle' font-size='14' "
        f"transform='rotate(-90 20 {height / 2})'>{html.escape(labels[1])}</text>"
        f"{legend}</svg>\n",
        encoding="utf-8",
    )


def write_variance_svg(
    path: Path, component_names: list[str], ratios: np.ndarray[Any, Any]
) -> None:
    width, height, padding = 900, 500, 72
    maximum = max(float(np.max(ratios)), 0.01)
    bar_width = (width - 2 * padding) / max(len(ratios), 1)
    bars = []
    for index, (name, ratio) in enumerate(zip(component_names, ratios, strict=True)):
        bar_height = float(ratio) / maximum * (height - 2 * padding)
        left = padding + index * bar_width + bar_width * 0.15
        top = height - padding - bar_height
        bars.append(
            f"<rect x='{left:.2f}' y='{top:.2f}' width='{bar_width * 0.7:.2f}' "
            f"height='{bar_height:.2f}' fill='#155e75'><title>{html.escape(name)}: "
            f"{float(ratio) * 100:.2f}%</title></rect>"
            f"<text x='{left + bar_width * 0.35:.2f}' y='{height - padding + 20}' "
            f"text-anchor='middle' font-size='11'>{html.escape(name)}</text>"
        )
    path.write_text(
        _svg_start(width, height, "Explained variance")
        + f"<text x='{width / 2}' y='30' text-anchor='middle' font-size='22' "
        "font-weight='700'>Explained variance</text>"
        f"<line x1='{padding}' y1='{height - padding}' x2='{width - padding}' "
        f"y2='{height - padding}' stroke='#94a3b8'/>"
        f"<line x1='{padding}' y1='{padding}' x2='{padding}' y2='{height - padding}' "
        f"stroke='#94a3b8'/>{''.join(bars)}"
        f"<text x='20' y='{height / 2}' text-anchor='middle' font-size='14' "
        f"transform='rotate(-90 20 {height / 2})'>Variance ratio (max {maximum:.2f})</text>"
        "</svg>\n",
        encoding="utf-8",
    )


def write_dendrogram_svg(
    path: Path,
    sample_order: list[str],
    icoord: list[list[float]],
    dcoord: list[list[float]],
) -> None:
    width = max(1000, len(sample_order) * 18)
    height, top, bottom = 650, 55, 170
    maximum_x = max((value for row in icoord for value in row), default=1.0)
    maximum_y = max((value for row in dcoord for value in row), default=1.0)
    def x(value: float) -> float:
        return 30 + float(value) / maximum_x * (width - 60)

    def y(value: float) -> float:
        return height - bottom - float(value) / maximum_y * (height - bottom - top)

    branches = "".join(
        "<polyline points='"
        + " ".join(
            f"{x(x_value):.2f},{y(y_values[index]):.2f}"
            for index, x_value in enumerate(x_values)
        )
        + "' fill='none' stroke='#155e75' stroke-width='1.5'/>"
        for x_values, y_values in zip(icoord, dcoord, strict=True)
    )
    labels = "".join(
        f"<text x='{x(5 + index * 10):.2f}' y='{height - bottom + 10}' font-size='9' "
        f"text-anchor='end' transform='rotate(-62 {x(5 + index * 10):.2f} "
        f"{height - bottom + 10})'>{html.escape(sample)}</text>"
        for index, sample in enumerate(sample_order)
    )
    path.write_text(
        _svg_start(width, height, "Hierarchical sample dendrogram")
        + f"<text x='{width / 2}' y='30' text-anchor='middle' font-size='22' "
        f"font-weight='700'>Hierarchical sample dendrogram</text>{branches}{labels}</svg>\n",
        encoding="utf-8",
    )


def write_heatmap_svg(
    path: Path, sample_order: list[str], values: np.ndarray[Any, Any]
) -> None:
    size, offset = 900, 120
    plot_size = size - offset - 25
    cell = plot_size / max(len(sample_order), 1)
    rectangles = []
    for row, row_values in enumerate(values):
        for column, value in enumerate(row_values):
            rectangles.append(
                f"<rect x='{offset + column * cell:.2f}' y='{25 + row * cell:.2f}' "
                f"width='{cell + 0.1:.2f}' height='{cell + 0.1:.2f}' "
                f"fill='{_correlation_color(float(value))}'><title>"
                f"{html.escape(sample_order[row])} vs {html.escape(sample_order[column])}: "
                f"{float(value):.3f}</title></rect>"
            )
    path.write_text(
        _svg_start(size, size, "Sample correlation heatmap")
        + "<text x='18' y='450' text-anchor='middle' font-size='18' "
        "transform='rotate(-90 18 450)'>Samples in dendrogram order</text>"
        + "".join(rectangles)
        + "</svg>\n",
        encoding="utf-8",
    )


def _limits(values: np.ndarray[Any, Any]) -> tuple[float, float]:
    minimum, maximum = float(np.min(values)), float(np.max(values))
    if minimum == maximum:
        return minimum - 1.0, maximum + 1.0
    margin = (maximum - minimum) * 0.08
    return minimum - margin, maximum + margin


def _correlation_color(value: float) -> str:
    bounded = max(-1.0, min(1.0, value))
    target = (21, 94, 117) if bounded >= 0 else (190, 18, 60)
    strength = abs(bounded)
    channels = [round(255 + (channel - 255) * strength) for channel in target]
    return f"rgb({channels[0]},{channels[1]},{channels[2]})"


def _svg_start(width: int, height: int, title: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>"
        "<style>text{font-family:system-ui,sans-serif;fill:#17323a}</style>"
        f"<title>{html.escape(title)}</title><rect width='100%' height='100%' fill='white'/>"
    )
