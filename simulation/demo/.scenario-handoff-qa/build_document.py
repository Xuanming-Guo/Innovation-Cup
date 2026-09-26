"""Build the teammate fact sheet from its Markdown source; no harness execution."""
from pathlib import Path
import re
import sys

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Inches, Pt, RGBColor

SKILL = Path('/Users/sophiaji/.codex/plugins/cache/openai-primary-runtime/documents/26.826.12353/skills/documents')
sys.path.insert(0, str(SKILL / 'scripts'))
from table_geometry import apply_table_geometry

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / 'scenario-facts-for-teammate.md'
OUTPUT = BASE / 'scenario-facts-for-teammate.docx'

# standard_business_brief; memo_masthead with no rule.
# Named component overrides: Arial body for portable display; Hiragino Sans CJK;
# 10 pt table/source text; 23 pt title; 9 pt running furniture.
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)
sec.header_distance = sec.footer_distance = Inches(.492)

def style(name, size, color='202529', before=0, after=6, bold=False, line=1.1):
    st = doc.styles[name] if name in doc.styles else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    st.font.name, st.font.size = 'Arial', Pt(size)
    st.font.color.rgb = RGBColor.from_string(color)
    st.font.bold = bold
    st.font.italic = False
    fonts=st._element.get_or_add_rPr().rFonts
    for attr in list(fonts.attrib):
        if attr.endswith('Theme'): del fonts.attrib[attr]
    fonts.set(qn('w:eastAsia'), 'Hiragino Sans')
    for border in st._element.findall('.//' + qn('w:pBdr')):
        border.getparent().remove(border)
    fmt = st.paragraph_format
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    fmt.line_spacing = line
    fmt.widow_control = True
    return st

style('Normal', 11)
style('Title', 23, '0B2545', after=5, bold=True)
style('Subtitle', 10, '5B6570', after=12)
for name, size, color, before, after in [
    ('Heading 1',16,'2E74B5',16,8), ('Heading 2',13,'2E74B5',12,6),
    ('Heading 3',12,'1F4D78',8,4)]:
    style(name,size,color,before,after,True).paragraph_format.keep_with_next = True
style('Table Body',10,after=0,line=1.05)
style('Source Text',9,'5B6570',before=4,after=4,line=1.05)
style('Header',9,'5B6570',after=0)
style('Footer',9,'5B6570',after=0)
header = sec.header.paragraphs[0]
header.text = 'ALTO  /  SCENARIO FACTS'
footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
footer.add_run('Synthetic scenario  ·  ')
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'),'PAGE')
footer._p.append(field)

def inline(paragraph, text):
    for bit in re.split(r'(\*\*.*?\*\*|\[[^\]]+\]\([^)]+\))', text):
        if not bit:
            continue
        if bit.startswith('**') and bit.endswith('**'):
            paragraph.add_run(bit[2:-2]).bold = True
        elif bit.startswith('[') and '](' in bit:
            label, target = re.match(r'\[([^\]]+)\]\(([^)]+)\)', bit).groups()
            assert (BASE / target).resolve().exists(), target
            link = OxmlElement('w:hyperlink')
            link.set(qn('r:id'), paragraph.part.relate_to(target,RT.HYPERLINK,is_external=True))
            run = OxmlElement('w:r')
            prop = OxmlElement('w:rPr')
            color = OxmlElement('w:color'); color.set(qn('w:val'),'2E74B5'); prop.append(color)
            run.append(prop)
            value = OxmlElement('w:t'); value.text = label; run.append(value)
            link.append(run); paragraph._p.append(link)
        else:
            paragraph.add_run(bit)

def make_table(lines):
    rows = [[x.strip() for x in line.strip('|').split('|')] for line in lines]
    rows = [rows[0], *rows[2:]]
    table = doc.add_table(rows=len(rows), cols=3)
    table.autofit = False
    table.style = 'Table Grid'
    for i, values in enumerate(rows):
        for cell, value in zip(table.rows[i].cells, values):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]; p.style = doc.styles['Table Body']; inline(p,value)
            if i == 0:
                for run in p.runs: run.bold = True
                shd = OxmlElement('w:shd'); shd.set(qn('w:fill'),'F2F4F7'); cell._tc.get_or_add_tcPr().append(shd)
        trpr = table.rows[i]._tr.get_or_add_trPr()
        trpr.append(OxmlElement('w:cantSplit'))
        if i == 0: trpr.append(OxmlElement('w:tblHeader'))
    widths = [2870,1110,5380] if rows[0][1] == 'ID' else [3200,1450,4710]
    apply_table_geometry(table,widths,indent_dxa=120,
        cell_margins_dxa={'top':80,'bottom':80,'start':120,'end':120})

lines = SOURCE.read_text().splitlines()
i=0
source_mode=False
page_break_pending=False
after_table=False
while i<len(lines):
    line=lines[i].strip()
    if not line: i+=1; continue
    if line=='<!-- pagebreak -->':
        page_break_pending=True; i+=1; continue
    if line.startswith('|'):
        group=[]
        while i<len(lines) and lines[i].startswith('|'):
            group.append(lines[i]); i+=1
        make_table(group)
        after_table=True
        continue
    if line.startswith('# '):
        inline(doc.add_paragraph(style='Title'),line[2:])
    elif line.startswith('## '):
        paragraph=doc.add_paragraph(style='Heading 2')
        if page_break_pending:
            paragraph.paragraph_format.page_break_before=True
            paragraph.paragraph_format.space_before=Pt(0)
            page_break_pending=False
        inline(paragraph,line[3:])
        source_mode = line=='## Source records'
    else:
        name = 'Source Text' if source_mode else ('Subtitle' if line.startswith('Teammate handoff') else 'Normal')
        paragraph=doc.add_paragraph(style=name)
        if after_table:
            paragraph.paragraph_format.space_before=Pt(6)
            after_table=False
        inline(paragraph,line)
    i+=1

doc.core_properties.title = 'SoraWorks scenario facts'
doc.core_properties.subject = 'Exact synthetic identities, deadline change, priority change and shared-capacity conflict'
doc.core_properties.author = 'ALTO'
doc.core_properties.keywords = 'synthetic; scenario; Hikari; SSO; teammate handoff'
doc.save(OUTPUT)
print(OUTPUT)
