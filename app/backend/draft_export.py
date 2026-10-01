"""Owned saved-draft PDF export; content is printed literally, never interpreted as markup."""
from io import BytesIO
from threading import Lock
from fastapi import APIRouter, Depends, Request, Response, Query
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4
from app.backend.api import project
from app.backend.config import ROOT
from app.backend.security import current_user, fail

router = APIRouter(prefix='/api/projects')
_font_lock = Lock()

def draft_pdf(title, draft):
    with _font_lock:
        if 'PulseSans' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('PulseSans', str(ROOT / 'app/static/fonts/DejaVuSans.ttf')))
    supported = pdfmetrics.getFont('PulseSans').face.charToGlyph
    content = title + '\n' + draft['content']
    if any(ord(c) not in supported for c in content if c not in '\n\r\t'):
        fail(422, 'unsupported_pdf_character', 'This draft contains characters unsupported by the PDF font. Use a supported character or keep the text draft.')
    if any(ord(c) < 32 for c in content if c not in '\n\r\t'):
        fail(422, 'unsupported_pdf_character', 'Remove control characters before exporting this draft.')
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4, pageCompression=1)
    canvas.setTitle('Football Pulse - saved draft')
    width, height = A4
    page = 0
    def new_page():
        nonlocal page
        if page:
            canvas.showPage()
        page += 1
        canvas.setFont('PulseSans', 9)
        canvas.drawString(42, height-34, 'Football Pulse - saved draft / not approved for publishing')
        canvas.drawRightString(width-42, 24, str(page))
        return height-60
    y = new_page()
    lines = [title, f"Version {draft['version']} | {draft['content_type']} | mode: {draft['content_mode']}", ''] + draft['content'].replace('\r\n','\n').replace('\r','\n').split('\n')
    canvas.setFont('PulseSans', 10)
    for raw in lines:
        raw = raw.replace('\t','    ')
        # Wrap using measured glyph widths, including long unbroken input.
        chunks, part, measured = [], '', 0.0
        for char in raw:
            size = pdfmetrics.stringWidth(char,'PulseSans',10)
            if measured+size > width-84 and part:
                chunks.append(part); part=''; measured=0.0
            part += char; measured += size
        chunks.append(part)
        for line in chunks:
            if y < 48:
                y = new_page(); canvas.setFont('PulseSans',10)
            canvas.drawString(42,y,line)
            y -= 15
    canvas.save()
    return stream.getvalue()

@router.get('/{project_id}/draft/export.pdf')
def export_draft(project_id: str, request: Request, expected_version: int = Query(ge=1), user=Depends(current_user)):
    with request.app.state.database.transaction() as db:
        owned = project(db, project_id, user)
        row = db.execute('SELECT * FROM drafts WHERE project_id=?',(project_id,)).fetchone()
        if not row or not row['content'].strip():
            fail(404, 'draft_not_found', 'Save a nonempty draft before exporting.')
        if row['version'] != expected_version:
            fail(409, 'version_conflict', 'The saved draft changed. Reload it before exporting.')
        saved = dict(row)
        title = owned['title']
    return Response(draft_pdf(title,saved), media_type='application/pdf', headers={'Content-Disposition':'attachment; filename="football-pulse-draft.pdf"','Cache-Control':'no-store'})
