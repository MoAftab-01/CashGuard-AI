"""Accessible chart representations, using plotted values without new analytics."""

import re

import pandas as pd


def table_values(frame):
    """Render text literally in native tables, which otherwise interpret Markdown.

    Imported descriptions/categories must not create image requests, links or
    formatting directives. Use CommonMark code spans (including URL autolinks); numbers,
    dates and missing values stay typed. Never mutate the engine/display frame.
    """
    def literal(value):
        if not isinstance(value, str) or not value.strip():
            return value
        fence = "`" * (1 + max((len(run) for run in re.findall(r"`+", value)), default=0))
        # Padding is removed by CommonMark and protects leading/trailing backticks.
        return f"{fence} {value} {fence}"
    result = frame.map(literal)
    result.columns = [literal(column) for column in frame.columns]
    return result


def chart_alternative(figure):
    """Return a description and all source points, not inferred histogram counts.

    Keep this independent of Streamlit so alternatives can be checked against
    the actual figures. Missing values stay missing; no interpolation or totals.
    """
    title = figure.layout.title.text or "Financial chart"
    x_label = figure.layout.xaxis.title.text or "X"
    y_label = figure.layout.yaxis.title.text or "Y"
    rows = []
    names = []
    for index, trace in enumerate(figure.data):
        name = trace.name or f"Series {index + 1}"
        names.append(name)
        xs = list(trace.x) if trace.x is not None else []
        ys = list(trace.y) if trace.y is not None else []
        if trace.type == "heatmap":
            for y, values in zip(ys, trace.z):
                for x, value in zip(xs, values):
                    rows.append({"Series": name, x_label: x, y_label: y, "Count": value})
        elif trace.type == "histogram":
            for value in xs:
                rows.append({"Series": name, x_label: value})
        else:
            for x, y in zip(xs, ys):
                rows.append({"Series": name, x_label: x, y_label: y})
    description = f"{title}. Series: {', '.join(names) or 'none'}."
    if any(trace.type == "histogram" for trace in figure.data):
        description += " Table lists individual observations; visual histogram bins are not counts in this table."
    for shape in figure.layout.shapes or ():
        if shape.yref == "y" and shape.y0 == shape.y1:
            description += f" Horizontal reference ({y_label}): {shape.y0}."
        elif shape.xref == "x" and shape.x0 == shape.x1:
            description += f" Vertical reference ({x_label}): {shape.x0}."
    description += " Expand Chart data below for the plotted values in a readable table."
    return description, pd.DataFrame(rows)
