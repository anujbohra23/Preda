"""
Report generation using ReportLab (pure Python, no system dependencies).
Builds PDF programmatically — no HTML-to-PDF conversion needed.
"""
import os
import json
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── Colour palette ─────────────────────────────────────────────────────────────
BLUE        = colors.HexColor('#1d4ed8')
BLUE_LIGHT  = colors.HexColor('#dbeafe')
GREEN       = colors.HexColor('#065f46')
GREEN_LIGHT = colors.HexColor('#d1fae5')
RED         = colors.HexColor('#b91c1c')
RED_LIGHT   = colors.HexColor('#fef2f2')
AMBER       = colors.HexColor('#92400e')
AMBER_LIGHT = colors.HexColor('#fef3c7')
SLATE       = colors.HexColor('#475569')
SLATE_LIGHT = colors.HexColor('#f8fafc')
SLATE_MID   = colors.HexColor('#e2e8f0')
WHITE       = colors.white
BLACK       = colors.HexColor('#1e293b')


def utcnow_str():
    return datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')


# ── Style builder ──────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    custom = {
        'title': ParagraphStyle(
            'title',
            fontSize=20, textColor=BLUE,
            fontName='Helvetica-Bold',
            spaceAfter=4
        ),
        'subtitle': ParagraphStyle(
            'subtitle',
            fontSize=8.5, textColor=SLATE,
            fontName='Helvetica', spaceAfter=12
        ),
        'h2': ParagraphStyle(
            'h2',
            fontSize=13, textColor=BLUE,
            fontName='Helvetica-Bold',
            spaceBefore=18, spaceAfter=6,
            borderPadding=(0, 0, 4, 0),
        ),
        'h3': ParagraphStyle(
            'h3',
            fontSize=11, textColor=BLACK,
            fontName='Helvetica-Bold',
            spaceBefore=8, spaceAfter=4
        ),
        'body': ParagraphStyle(
            'body',
            fontSize=10, textColor=BLACK,
            fontName='Helvetica',
            spaceAfter=4, leading=15
        ),
        'small': ParagraphStyle(
            'small',
            fontSize=8.5, textColor=SLATE,
            fontName='Helvetica',
            spaceAfter=3, leading=12
        ),
        'disclaimer': ParagraphStyle(
            'disclaimer',
            fontSize=9, textColor=AMBER,
            fontName='Helvetica-Bold',
            spaceAfter=4, leading=13
        ),
        'label': ParagraphStyle(
            'label',
            fontSize=7.5, textColor=SLATE,
            fontName='Helvetica-Bold',
            spaceAfter=2,
        ),
        'bullet': ParagraphStyle(
            'bullet',
            fontSize=10, textColor=BLACK,
            fontName='Helvetica',
            spaceAfter=3, leading=14,
            leftIndent=12, bulletIndent=0,
        ),
        'footer': ParagraphStyle(
            'footer',
            fontSize=7.5, textColor=SLATE,
            fontName='Helvetica',
            alignment=TA_CENTER
        ),
    }
    return custom


# ── Patient Report ─────────────────────────────────────────────────────────────

def build_patient_report(session, intake, diseases,
                          chat_messages, retrievals):
    top_diseases = []
    for dr in diseases[:5]:
        explanation = {}
        if dr.explanation_json:
            try:
                explanation = json.loads(dr.explanation_json)
            except Exception:
                pass
        top_diseases.append({
            'rank':             dr.rank,
            'disease_name':     dr.disease.disease_name,
            'icd_code':         dr.disease.icd_code or '',
            'short_desc':       dr.disease.short_desc or '',
            'similarity_score': dr.similarity_score,
            'matching_phrases': explanation.get('matching_phrases', []),
        })

    citations = _build_citations(retrievals)

    return {
        'report_type':   'patient',
        'generated_at':  utcnow_str(),
        'session_title': session.title,
        'session_id':    session.id,
        'intake':        intake,
        'top_diseases':  top_diseases,
        'citations':     citations,
        'chat_count':    len(chat_messages),
    }


def build_pharmacy_report(session, intake, diseases,
                           chat_messages, retrievals):
    top_diseases = []
    for dr in diseases[:10]:
        explanation = {}
        if dr.explanation_json:
            try:
                explanation = json.loads(dr.explanation_json)
            except Exception:
                pass
        top_diseases.append({
            'rank':             dr.rank,
            'disease_name':     dr.disease.disease_name,
            'icd_code':         dr.disease.icd_code or '',
            'short_desc':       dr.disease.short_desc or '',
            'similarity_score': round(dr.similarity_score * 100, 1),
            'matching_phrases': explanation.get('matching_phrases', []),
        })

    rag_findings = []
    for msg in chat_messages:
        if msg.role == 'assistant' and not msg.safety_triggered:
            msg_retrievals = [
                r for r in retrievals
                if r.chat_message_id == msg.id
            ]
            rag_findings.append({
                'content':   msg.content[:500],
                'citations': [r.citation_label for r in msg_retrievals],
            })

    citations = _build_citations(retrievals)

    return {
        'report_type':   'pharmacy',
        'generated_at':  utcnow_str(),
        'session_title': session.title,
        'session_id':    session.id,
        'intake':        intake,
        'top_diseases':  top_diseases,
        'rag_findings':  rag_findings[:5],
        'citations':     citations,
    }


def _build_citations(retrievals) -> list[dict]:
    seen = set()
    citations = []
    for r in retrievals:
        key = (r.citation_label, r.source_doc_name)
        if key not in seen:
            seen.add(key)
            citations.append({
                'label':      r.citation_label,
                'source_doc': r.source_doc_name or 'Document',
                'excerpt':    r.chunk.chunk_text[:200] if r.chunk else '',
            })
    return citations


# ── PDF renderers ──────────────────────────────────────────────────────────────

def render_report_pdf(report_type: str, context: dict) -> bytes:
    if report_type == 'patient':
        return _render_patient_pdf(context)
    return _render_pharmacy_pdf(context)


def _render_patient_pdf(ctx: dict) -> bytes:
    buffer = BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm
    )
    s     = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Paragraph('⚕ Patient Health Summary', s['title']))
    story.append(Paragraph(
        f"Session: {ctx['session_title']} &nbsp;|&nbsp; "
        f"Generated: {ctx['generated_at']}",
        s['subtitle']
    ))
    story.append(HRFlowable(
        width='100%', thickness=2,
        color=BLUE, spaceAfter=10
    ))

    # ── Disclaimer box ────────────────────────────────────────────────────
    disclaimer_data = [[
        Paragraph(
            '<b>⚠ NOT MEDICAL ADVICE.</b> This document is for informational '
            'purposes only and does not constitute a medical diagnosis, '
            'prescription, or treatment recommendation. Always consult a '
            'qualified healthcare professional.',
            s['disclaimer']
        )
    ]]
    disclaimer_table = Table(disclaimer_data, colWidths=['100%'])
    disclaimer_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), AMBER_LIGHT),
        ('BOX',        (0,0), (-1,-1), 1, colors.HexColor('#f59e0b')),
        ('ROUNDEDCORNERS', [4]),
        ('PADDING',    (0,0), (-1,-1), 8),
    ]))
    story.append(disclaimer_table)
    story.append(Spacer(1, 12))

    # ── Intake ────────────────────────────────────────────────────────────
    story.append(Paragraph('Your Reported Symptoms', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=8))

    intake_rows = []
    field_labels = {
        'age': 'Age', 'sex': 'Biological Sex',
        'chief_complaint': 'Chief Complaint',
        'duration': 'Duration',
        'medications': 'Medications',
        'allergies': 'Allergies',
        'additional_notes': 'Additional Notes',
    }
    for key, label in field_labels.items():
        value = ctx['intake'].get(key, '')
        if value:
            intake_rows.append([
                Paragraph(label, s['label']),
                Paragraph(str(value), s['body']),
            ])

    if intake_rows:
        intake_table = Table(
            intake_rows,
            colWidths=[40*mm, 130*mm]
        )
        intake_table.setStyle(TableStyle([
            ('VALIGN',     (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING',    (0,0), (-1,-1), 3),
        ]))
        story.append(intake_table)

    # ── Top conditions ────────────────────────────────────────────────────
    story.append(Paragraph('Possible Conditions to Discuss', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=6))
    story.append(Paragraph(
        'These are informational matches based on symptom similarity. '
        'Higher % = more symptom overlap. This is <b>not</b> a diagnosis.',
        s['small']
    ))
    story.append(Spacer(1, 6))

    for d in ctx['top_diseases']:
        score_pct = round(d['similarity_score'] * 100, 1)

        # Row: rank + name + score
        header_data = [[
            Paragraph(
                f"<b>#{d['rank']}  {d['disease_name']}</b>  "
                f"<font color='#64748b' size='8'>{d['icd_code']}</font>",
                s['body']
            ),
            Paragraph(
                f"<b>{score_pct}%</b> match",
                ParagraphStyle('score', fontSize=10,
                               textColor=BLUE, fontName='Helvetica-Bold',
                               alignment=TA_RIGHT)
            ),
        ]]
        header_table = Table(header_data, colWidths=[130*mm, 40*mm])
        header_table.setStyle(TableStyle([
            ('VALIGN',   (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING',  (0,0), (-1,-1), 0),
        ]))

        card_content = [
            [header_table],
        ]
        if d.get('short_desc'):
            card_content.append([
                Paragraph(d['short_desc'], s['small'])
            ])
        if d.get('matching_phrases'):
            terms = '  '.join(d['matching_phrases'][:8])
            card_content.append([
                Paragraph(
                    f"<font color='#854d0e' size='8'>"
                    f"Matched terms: {terms}</font>",
                    s['small']
                )
            ])

        card = Table(card_content, colWidths=['100%'])
        card.setStyle(TableStyle([
            ('BOX',       (0,0), (-1,-1), 0.5, SLATE_MID),
            ('BACKGROUND',(0,0), (-1,-1), SLATE_LIGHT),
            ('PADDING',   (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,-1), (-1,-1), 10),
        ]))
        story.append(card)
        story.append(Spacer(1, 6))

    # ── Urgent care ───────────────────────────────────────────────────────
    story.append(Paragraph('When to Seek Urgent Care', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=6))
    urgent_items = [
        'Chest pain, pressure, or tightness',
        'Difficulty breathing or shortness of breath',
        'Sudden severe headache unlike any before',
        'Facial drooping, arm weakness, or slurred speech',
        'Thoughts of harming yourself or others',
        'Severe allergic reaction (throat swelling)',
    ]
    urgent_data = [[
        Paragraph(
            '<b>Call emergency services (911 / 999 / 112) immediately if:</b>',
            s['disclaimer']
        )
    ]]
    for item in urgent_items:
        urgent_data.append([Paragraph(f'• {item}', s['bullet'])])

    urgent_table = Table(urgent_data, colWidths=['100%'])
    urgent_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), RED_LIGHT),
        ('BOX',        (0,0), (-1,-1), 0.5, RED),
        ('PADDING',    (0,0), (-1,-1), 8),
    ]))
    story.append(urgent_table)
    story.append(Spacer(1, 10))

    # ── Questions to ask ──────────────────────────────────────────────────
    story.append(Paragraph('Questions to Ask Your Doctor', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=6))
    questions = [
        f"Could my symptoms be related to "
        f"{ctx['top_diseases'][0]['disease_name']}?"
        if ctx['top_diseases'] else
        "What condition might be causing my symptoms?",
        "What tests would help clarify the cause of my symptoms?",
        "How urgent is it to investigate these symptoms further?",
        "Are there lifestyle changes that might help?",
    ]
    if ctx['intake'].get('medications'):
        questions.append(
            "Are there interactions between my medications "
            "and these possible conditions?"
        )

    q_data = [[Paragraph(f'• {q}', s['bullet'])] for q in questions]
    q_table = Table(q_data, colWidths=['100%'])
    q_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GREEN_LIGHT),
        ('BOX',        (0,0), (-1,-1), 0.5, colors.HexColor('#86efac')),
        ('PADDING',    (0,0), (-1,-1), 8),
    ]))
    story.append(q_table)

    # ── Citations ─────────────────────────────────────────────────────────
    if ctx.get('citations'):
        story.append(Paragraph('Document Sources', s['h2']))
        story.append(HRFlowable(width='100%', thickness=0.5,
                                 color=SLATE_MID, spaceAfter=6))
        for c in ctx['citations']:
            excerpt = f' — "{c["excerpt"][:120]}…"' if c.get('excerpt') else ''
            story.append(Paragraph(
                f"<b>{c['label']}</b> {c['source_doc']}{excerpt}",
                s['small']
            ))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=6))
    story.append(Paragraph(
        'HealthAssist MVP — Informational Tool Only | '
        'NOT a medical diagnosis | ' + ctx['generated_at'],
        s['footer']
    ))

    doc.build(story)
    return buffer.getvalue()


def _render_pharmacy_pdf(ctx: dict) -> bytes:
    buffer = BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm
    )
    s     = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Paragraph(
        '💊 Informational Pharmacy Summary', s['title']
    ))
    story.append(Paragraph(
        f"Session: {ctx['session_title']} | "
        f"Generated: {ctx['generated_at']}",
        s['subtitle']
    ))
    story.append(HRFlowable(
        width='100%', thickness=2,
        color=GREEN, spaceAfter=10
    ))

    # ── Big disclaimer ────────────────────────────────────────────────────
    disc_data = [[Paragraph(
        '<b>⛔ NOT A PRESCRIPTION. NOT A CLINICAL DIAGNOSIS.</b><br/>'
        'This is an informational summary generated from patient '
        'self-reported data and uploaded documents. All information '
        'must be independently verified before any clinical action.',
        ParagraphStyle('disc2', fontSize=9, textColor=RED,
                       fontName='Helvetica-Bold', leading=13)
    )]]
    disc_table = Table(disc_data, colWidths=['100%'])
    disc_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), RED_LIGHT),
        ('BOX',        (0,0), (-1,-1), 1.5, RED),
        ('PADDING',    (0,0), (-1,-1), 10),
    ]))
    story.append(disc_table)
    story.append(Spacer(1, 12))

    # ── Intake ────────────────────────────────────────────────────────────
    story.append(Paragraph('Patient-Reported Intake', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=GREEN_LIGHT, spaceAfter=6))
    field_labels = {
        'age': 'Age', 'sex': 'Sex',
        'chief_complaint': 'Chief Complaint',
        'duration': 'Duration',
        'medications': 'Medications',
        'allergies': 'Allergies',
        'additional_notes': 'Notes',
    }
    intake_rows = []
    for key, label in field_labels.items():
        value = ctx['intake'].get(key, '')
        if value:
            intake_rows.append([
                Paragraph(label, s['label']),
                Paragraph(str(value), s['body']),
            ])
    if intake_rows:
        t = Table(intake_rows, colWidths=[38*mm, 132*mm])
        t.setStyle(TableStyle([
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING',    (0,0), (-1,-1), 3),
        ]))
        story.append(t)

    # ── Top 10 conditions table ───────────────────────────────────────────
    story.append(Paragraph('Top Condition Candidates', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=GREEN_LIGHT, spaceAfter=6))

    table_data = [[
        Paragraph('Rank', s['label']),
        Paragraph('Condition', s['label']),
        Paragraph('ICD', s['label']),
        Paragraph('Score', s['label']),
        Paragraph('Evidence Terms', s['label']),
    ]]
    for d in ctx['top_diseases']:
        terms = ', '.join(d['matching_phrases'][:4]) if d['matching_phrases'] else '—'
        table_data.append([
            Paragraph(str(d['rank']), s['small']),
            Paragraph(f"<b>{d['disease_name']}</b>", s['small']),
            Paragraph(d['icd_code'], s['small']),
            Paragraph(f"{d['similarity_score']}%",
                      ParagraphStyle('score_cell', fontSize=9,
                                     textColor=BLUE, fontName='Helvetica-Bold')),
            Paragraph(terms, s['small']),
        ])

    col_widths = [12*mm, 58*mm, 18*mm, 18*mm, 64*mm]
    cond_table = Table(table_data, colWidths=col_widths,
                       repeatRows=1)
    cond_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), GREEN_LIGHT),
        ('TEXTCOLOR',     (0,0), (-1,0), GREEN),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0), 7.5),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [WHITE, SLATE_LIGHT]),
        ('GRID',          (0,0), (-1,-1), 0.25, SLATE_MID),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ('PADDING',       (0,0), (-1,-1), 5),
    ]))
    story.append(cond_table)
    story.append(Paragraph(
        'Score = semantic similarity between intake and condition description. '
        'Does not indicate diagnosis probability.',
        s['small']
    ))

    # ── RAG findings ──────────────────────────────────────────────────────
    if ctx.get('rag_findings'):
        story.append(Paragraph('Document-Derived Findings', s['h2']))
        story.append(HRFlowable(width='100%', thickness=0.5,
                                 color=GREEN_LIGHT, spaceAfter=6))
        for finding in ctx['rag_findings']:
            cites = ' '.join(finding['citations']) if finding['citations'] else ''
            finding_data = [[
                Paragraph(
                    f"{finding['content'][:400]} "
                    f"<font color='#059669'><b>{cites}</b></font>",
                    s['small']
                )
            ]]
            ft = Table(finding_data, colWidths=['100%'])
            ft.setStyle(TableStyle([
                ('BACKGROUND',  (0,0), (-1,-1), GREEN_LIGHT),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
                ('PADDING',     (0,0), (-1,-1), 7),
                ('BOX',         (0,0), (-1,-1), 0.5,
                 colors.HexColor('#6ee7b7')),
            ]))
            story.append(ft)
            story.append(Spacer(1, 4))

    # ── Citations ─────────────────────────────────────────────────────────
    if ctx.get('citations'):
        story.append(Paragraph('Source Citations', s['h2']))
        story.append(HRFlowable(width='100%', thickness=0.5,
                                 color=GREEN_LIGHT, spaceAfter=6))
        for c in ctx['citations']:
            excerpt = f'— "{c["excerpt"][:120]}…"' if c.get('excerpt') else ''
            story.append(Paragraph(
                f"<b>{c['label']}</b> {c['source_doc']} {excerpt}",
                s['small']
            ))

    # ── Clinical disclaimer ───────────────────────────────────────────────
    story.append(Paragraph('Clinical Disclaimer', s['h2']))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=GREEN_LIGHT, spaceAfter=6))
    story.append(Paragraph(
        'This summary was generated by an automated informational tool. '
        'It is based entirely on patient self-reported symptoms and uploaded '
        'documents. Reported medications and allergies have not been clinically '
        'verified. Condition candidates are derived from semantic similarity '
        'matching and do not represent clinical assessment or medical opinion. '
        'No prescriptive or treatment authority is implied. All clinical '
        'decisions must be made by a licensed healthcare professional.',
        s['body']
    ))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=SLATE_MID, spaceAfter=6))
    story.append(Paragraph(
        'HealthAssist MVP — NOT a prescription or diagnosis | '
        + ctx['generated_at'],
        s['footer']
    ))

    doc.build(story)
    return buffer.getvalue()


def save_pdf(pdf_bytes: bytes, session_id: int,
             report_type: str, upload_folder: str) -> str:
    reports_dir = os.path.join(
        upload_folder, 'reports', str(session_id)
    )
    os.makedirs(reports_dir, exist_ok=True)
    filename    = f"{report_type}_report_{session_id}.pdf"
    stored_path = os.path.join(reports_dir, filename)
    with open(stored_path, 'wb') as f:
        f.write(pdf_bytes)
    return stored_path