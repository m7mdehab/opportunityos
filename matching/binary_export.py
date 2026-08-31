import io
import os
from typing import Optional, List
from matching.models import TailoredArtifact, ArtifactType
import docx
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

class BinaryArtifactExporter:
    @staticmethod
    def export_to_docx(artifact: TailoredArtifact, output_path: Optional[str] = None) -> bytes:
        doc = docx.Document()
        
        # Page Margins: Standard 0.75 in for clean ATS presentation
        for s in doc.sections:
            s.top_margin = Inches(0.75)
            s.bottom_margin = Inches(0.75)
            s.left_margin = Inches(0.75)
            s.right_margin = Inches(0.75)

        # Document Title / Header
        title_p = doc.add_paragraph()
        title_run = title_p.add_run(artifact.title)
        title_run.bold = True
        title_run.font.size = Pt(16)
        title_run.font.name = "Arial"

        for sec in artifact.sections:
            if sec.heading:
                h_p = doc.add_paragraph()
                h_run = h_p.add_run(sec.heading)
                h_run.bold = True
                h_run.font.size = Pt(12)
                h_run.font.name = "Arial"

            if sec.content:
                p = doc.add_paragraph()
                r = p.add_run(sec.content)
                r.font.size = Pt(10.5)
                r.font.name = "Arial"

            for item in sec.items:
                bp = doc.add_paragraph(style='List Bullet')
                br = bp.add_run(item)
                br.font.size = Pt(10)
                br.font.name = "Arial"

        bio = io.BytesIO()
        doc.save(bio)
        content = bio.getvalue()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(content)

        return content

    @staticmethod
    def export_to_pdf(artifact: TailoredArtifact, output_path: Optional[str] = None) -> bytes:
        bio = io.BytesIO()
        doc = SimpleDocTemplate(
            bio,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54,
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            fontName='Helvetica',
            spaceAfter=6,
        )
        bullet_style = ParagraphStyle(
            'Bullet',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            fontName='Helvetica',
            leftIndent=15,
            spaceAfter=3,
        )

        story = []
        story.append(Paragraph(artifact.title, title_style))

        for sec in artifact.sections:
            if sec.heading:
                story.append(Paragraph(sec.heading, heading_style))
            if sec.content:
                story.append(Paragraph(sec.content.replace("\n", "<br/>"), body_style))
            for item in sec.items:
                story.append(Paragraph(f"- {item}", bullet_style))

        doc.build(story)
        content = bio.getvalue()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(content)

        return content
