"""The three committed ATS-safe templates (BRIEF-FR-006 D1, ADR-0017):
Classic, Compact, and Modern. Each is committed DATA (a `Template`
instance below), not code: `matching/binary_export.py`'s DOCX/PDF
exporters render the exact same `TailoredArtifact` (built from
`matching.document_model`) three times, varying only font choice, sizes,
and spacing per template. All three are single column, use real heading
styles (no manual bold-as-heading hacks beyond the styling every template
already needs), use one consistent font family throughout the document,
and never use a table for layout or a text box -- `matching/binary_export.py`
never calls `doc.add_table()` and reportlab's `Table` flowable is never
imported.

PDF font names are restricted to reportlab's built-in Base-14 set
(Helvetica/Helvetica-Bold, Times-Roman/Times-Bold, Courier/Courier-Bold) so
no font file needs to be embedded or installed -- introducing a new font
dependency is out of scope for this order.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Template:
    """One ATS-safe rendering profile. `docx_font` is a font *name string*
    python-docx writes into the run properties (no embedding); `pdf_font`/
    `pdf_font_bold` must be reportlab Base-14 names."""
    name: str
    docx_font: str
    pdf_font: str
    pdf_font_bold: str
    title_size_pt: float
    heading_size_pt: float
    body_size_pt: float
    bullet_size_pt: float
    margin_in: float  # DOCX page margin, inches
    margin_pt: float  # PDF page margin, points


CLASSIC = Template(
    name="classic",
    docx_font="Arial",
    pdf_font="Helvetica",
    pdf_font_bold="Helvetica-Bold",
    title_size_pt=16,
    heading_size_pt=12,
    body_size_pt=10.5,
    bullet_size_pt=10,
    margin_in=0.75,
    margin_pt=54,
)

COMPACT = Template(
    name="compact",
    docx_font="Calibri",
    pdf_font="Helvetica",
    pdf_font_bold="Helvetica-Bold",
    title_size_pt=14,
    heading_size_pt=11,
    body_size_pt=9.5,
    bullet_size_pt=9,
    margin_in=0.5,
    margin_pt=36,
)

MODERN = Template(
    name="modern",
    docx_font="Georgia",
    pdf_font="Times-Roman",
    pdf_font_bold="Times-Bold",
    title_size_pt=17,
    heading_size_pt=13,
    body_size_pt=10.5,
    bullet_size_pt=10,
    margin_in=0.85,
    margin_pt=60,
)

TEMPLATES: dict[str, Template] = {
    "classic": CLASSIC,
    "compact": COMPACT,
    "modern": MODERN,
}

DEFAULT_TEMPLATE = CLASSIC


def get_template(name: str | None) -> Template:
    if not name:
        return DEFAULT_TEMPLATE
    try:
        return TEMPLATES[name.casefold()]
    except KeyError as exc:
        raise ValueError(f"unknown template {name!r}; valid: {sorted(TEMPLATES)}") from exc
