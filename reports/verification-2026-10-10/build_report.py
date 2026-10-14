"""Create the human-readable test report from this run's saved evidence."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, PageBreak, KeepTogether)
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'output' / 'pdf' / 'signir-check-test-report-2026-10-10.pdf'
V = json.loads((HERE / 'verification.json').read_text(encoding='utf-8'))
R = json.loads((HERE / 'evaluation' / 'report.json').read_text(encoding='utf-8'))
N = json.loads((HERE / 'natural-summary.json').read_text(encoding='utf-8'))
B = json.loads((HERE / 'baseline-parity.json').read_text(encoding='utf-8'))

INK = colors.HexColor('#163044')
MUTED = colors.HexColor('#50616E')
BLUE = colors.HexColor('#12657A')
PALE = colors.HexColor('#EDF5F7')
LINE = colors.HexColor('#D5DEE3')
AMBER = colors.HexColor('#9A621C')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle('Kicker', fontName='Helvetica-Bold', fontSize=9,
                          leading=12, textColor=BLUE, spaceAfter=10))
styles.add(ParagraphStyle('TitleX', fontName='Helvetica-Bold', fontSize=27,
                          leading=31, textColor=INK, spaceAfter=13))
styles.add(ParagraphStyle('SubX', fontName='Helvetica', fontSize=12,
                          leading=17, textColor=MUTED, spaceAfter=15))
styles.add(ParagraphStyle('HeadX', fontName='Helvetica-Bold', fontSize=14,
                          leading=18, textColor=INK, spaceBefore=13, spaceAfter=8))
styles.add(ParagraphStyle('BodyX', fontName='Helvetica', fontSize=10,
                          leading=14.5, textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle('SmallX', fontName='Helvetica', fontSize=8.5,
                          leading=11.8, textColor=MUTED, spaceAfter=6))
styles.add(ParagraphStyle('CellX', fontName='Helvetica', fontSize=9,
                          leading=12.5, textColor=INK))
styles.add(ParagraphStyle('CellHeadX', fontName='Helvetica-Bold', fontSize=9,
                          leading=12, textColor=INK))
styles.add(ParagraphStyle('MetricX', fontName='Helvetica-Bold', fontSize=22,
                          leading=26, textColor=BLUE))

WIDTH = A4[0] - 88
story = []


def p(text, style='BodyX'):
    return Paragraph(text, styles[style])


def add(text, style='BodyX'):
    story.append(p(text, style))


def table(headers, rows, widths):
    data = [[p(escape(str(x)), 'CellHeadX') for x in headers]]
    data += [[p(escape(str(x)), 'CellX') for x in row] for row in rows]
    t = Table(data, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PALE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 0), (-1, 0), .65, LINE),
        ('LINEBELOW', (0, 1), (-1, -1), .35, LINE),
    ]))
    story.append(t)
    story.append(Spacer(1, 7))


def page(title, subtitle, number):
    if number > 1:
        story.append(PageBreak())
    add(f'SIGNIR-CHECK  /  VERIFICATION  /  {number:02}', 'Kicker')
    add(title, 'TitleX')
    add(subtitle, 'SubX')


page('A tested research foundation',
     'Fresh test run - October 10, 2026 - Independent study by Sanchit and Vedant', 1)
add('<b>Yes, this is a step forward.</b> The program now provides a working way to '
    'extract selected facts, compare them, explain results, and run repeatable '
    'experiments. Its current readers still need substantial work before they can '
    'assess the available natural gloss data.')

metrics = Table([
    [p('25 / 25', 'MetricX'), p('20 / 20', 'MetricX'), p('0 / 643', 'MetricX')],
    [p('Existing tests passed', 'CellX'), p('Controlled errors detected', 'CellX'),
     p('Natural pairs assessed*', 'CellX')],
], colWidths=[WIDTH/3]*3)
metrics.setStyle(TableStyle([('VALIGN', (0,0),(-1,-1),'TOP'),
                            ('TOPPADDING',(0,0),(-1,-1),7),
                            ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
story.extend([metrics, Spacer(1, 8)])
add('*Every one of the five checks returned UNKNOWN for each natural pair. '
    'These three measures answer different questions and are not comparable accuracy scores.', 'SmallX')

add('What this run verified', 'HeadX')
table(['Check', 'Fresh outcome'], [
    ['Existing automated suite', '25 passed; 0 failures; 0 errors.'],
    ['Controlled evaluation', '160/160 expected statuses reproduced across 32 test pairs.'],
    ['Extraction on authored specifications', '320/320 side/check values agreed with fixture gold.'],
    ['Baseline compatibility', f'{B["comparisons"]} comparisons with earlier Sign F1; {B["differences"]} differences.'],
    ['Deliberately invalid runs', '4/4 correctly rejected with the expected error exit.'],
    ['One-attempt correction', 'Both saved examples ran; the deliberate regression was recorded.'],
    ['Installed package and source integrity', 'Installed smoke test passed; 12 Python modules match source.'],
], [178, WIDTH-178])
add('What the results establish', 'HeadX')
add('The software follows its specified rules on the tested cases. The controlled '
    'examples are artificial and use explicit annotations. They do not establish '
    'natural-ASL understanding, grammaticality, or translation quality.')
add('The product code and original corpus inputs were not changed. All reported '
    'outcomes were generated again for this request; no old result was presented '
    'as a fresh test.', 'SmallX')

page('How we tested the program',
     'Executable checks, deliberate failure cases, and preserved evidence.', 2)
add('1. Run the complete existing test suite', 'HeadX')
table(['Group', 'Tests', 'Behavior exercised'], [
    ['Core fact checking', '14', 'Evidence positions, missing information, negation scope, number attachments, role reversals, repeated labels, pronouns, unsupported numbers and record versions.'],
    ['Data and research workflow', '9', 'Transitive duplicate grouping, split conflicts, corpus joins, baseline behavior, gold-free coverage reporting, calibration, false-alarm denominators, frozen inputs and one-call correction.'],
    ['Command-line integration', '2', 'Demo and JSON checking, then example creation, preparation, batch checking, freeze, evaluation, feasibility and correction through real commands.'],
], [128, 42, WIDTH-170])
add('Tests used actual functions and command-line processes. Expected outcomes '
    'were literal assertions or authored fixture specifications. The correction '
    'call-count test used a small recording callable to verify one attempt.')

add('2. Check meaningful edge cases', 'HeadX')
table(['Case', 'Expected behavior', 'Observed'], [
    ['English says 3 apples; gloss says 9 APPLE', 'Number MISMATCH', 'As expected'],
    ['Negative English; gloss has no negative marker', 'Negation UNKNOWN', 'As expected'],
    ['3 apples / 2 books become 2 APPLE / 3 BOOK', 'Number MISMATCH', 'As expected'],
    ['Explicit agent and patient annotations reverse', 'Role MISMATCH', 'As expected'],
    ['Names change order without role annotations', 'Roles UNKNOWN', 'As expected'],
], [WIDTH-228, 145, 83])

add('3. Deliberately challenge the safeguards', 'HeadX')
add('On separate copies, we changed input bytes, changed the stored rule signature, '
    'changed a baseline threshold, and assigned duplicate English examples to '
    'opposing splits. <b>All four runs were rejected with exit code 2</b> and the '
    'expected reason. The original files were preserved.')
add('Exit code 2 is a successful safeguard test here: the program was expected '
    'to reject the input. It is not counted as a failed test.', 'SmallX')

page('Controlled results',
     'A replay of the original frozen experiment, without changing its rules.', 3)
add('We rebuilt 64 synthetic examples and prepared eight source families. There '
    'were 32 development and 32 test examples. The regenerated input hash exactly '
    'matched the original freeze. Evaluation checked that freeze and scored only '
    'the 32 test examples; thresholds remained those selected from development data.')
add('The test set contains eight unchanged synthetic references, 20 explicit '
    'errors, and four removed-negation-marker cases. Removing a marker expects '
    'UNKNOWN, not an automatic mismatch.')

labels = {'entities':'Person / thing', 'action':'Action', 'negation':'Explicit polarity',
          'numbers':'Number', 'roles':'Annotated roles'}
error_rows = []
for x in R['controlled_errors']:
    error_rows.append([labels[x['error_type']], f'{x["detected"]}/{x["total"]}',
                       f'{x["sign_f1_detected"]}/{x["sign_f1_assessed"]}',
                       f'{x["word_f1_detected"]}/{x["word_f1_assessed"]}'])
table(['Known change', 'Checker', 'Sign F1', 'Raw word F1'], error_rows,
      [WIDTH-264, 88, 88, 88])
add('All 20 primary errors were detected. None were missed as MATCH or UNKNOWN. '
    'All 160 expected check statuses agreed, including 20 expected UNKNOWN results. '
    'Assessable check coverage was <b>140/160 = 87.5%</b>.')
add('There were no MISMATCH results on the eight unchanged synthetic examples. '
    'There were no qualified reviewed unchanged natural examples, so a natural '
    'false-alarm rate was not measured.')

add('How to read the comparison', 'HeadX')
add('Twelve explicit errors received Sign F1 = 1.0 but were detected by the '
    'checker. The old metric can discard digits and information in annotation '
    'labels. These examples expose that limitation within the tested notation.')
add('<b>Raw word F1 also detected all 20 errors.</b> This experiment therefore '
    'does not show a detection advantage over that baseline. The checker provides '
    'an additional explanation of the affected fact and its supporting words.')
add('The 320/320 gold agreement result is agreement with authored synthetic '
    'specifications, not independent natural-ASL annotation. Test and development '
    'families share a narrow grammar; no generalization or statistical-significance '
    'claim follows from these counts.', 'SmallX')

page('Natural data and next steps',
     'The real-data limitation is explicit, measurable, and still unresolved.', 4)
add('Natural-output audit', 'HeadX')
add('We freshly imported 643 saved outputs from one fixed earlier generation run, '
    'restored document IDs through exact source/reference joins, prepared grouped '
    'data, and ran the feasibility audit. Detailed corpus text stayed in private storage.')
add('<b>All 3,215 pair-level checks were UNKNOWN</b> (643 pairs x five checks). '
    'Both readers also returned unknown for every field. The present grammar and '
    'vocabulary cannot assess these inputs. This is a limitation of our extractors, '
    'not evidence that those translations are incorrect or that ASL lacks the facts.')
add('No independently reviewed fact records were available for this data. Natural '
    'extraction accuracy, error detection, false alarms and error causes remain '
    'unmeasured. The audit is descriptive; no synthetic threshold was applied.')

add('Correction experiment', 'HeadX')
table(['Saved example', 'Attempts', 'Observed result'], [
    ['Number repair', '1', 'Number MISMATCH became MATCH; no recorded regression.'],
    ['Repair with a new mistake', '1', 'Number improved, but the person changed; an entity regression was recorded.'],
], [135, 57, WIDTH-192])
add('These were exact saved responses, not a live generator. The experiment '
    'tests the workflow and regression accounting, not improved ASL quality.', 'SmallX')

add('What this enables next', 'HeadX')
add('Use this tested pipeline to evaluate a broader fact reader on a small, '
    'independently annotated development sample. English and gloss must still '
    'be read separately. A DGX Spark session could run one candidate model, but '
    'this test run used no GPU or new model. Reliable annotations and supported '
    'gloss interpretation are the immediate prerequisites.')

add('Evidence and reproduction', 'HeadX')
add('The companion <b>README.md</b> in <b>reports/verification-2026-10-10/</b> '
    'lists the methods, commands, expected exit codes and log files. '
    '<b>verification.json</b> records input/code hashes, the environment and '
    'outcomes. Detailed synthetic results are in <b>evaluation/</b>; '
    '<b>natural-summary.json</b> contains safe aggregates only.', 'SmallX')
add(f'Environment: {escape(V["python"])}; package {V["package_version"]}. '
    'The host emitted a Python executable-location warning, but all commands '
    'returned their expected exit codes. Source and original-input hashes were '
    'unchanged. Installed module hashes matched the source.', 'SmallX')


def footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(LINE)
    canvas.line(44, 38, w-44, 38)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(44, 25, 'SignIR-Check | Fresh verification | 2026-10-10')
    canvas.drawRightString(w-44, 25, f'{doc.page} / 4')
    canvas.restoreState()


OUT.parent.mkdir(parents=True, exist_ok=True)
doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=44, leftMargin=44,
                        topMargin=39, bottomMargin=53,
                        title='SignIR-Check: Test Results and Methods',
                        author='Sanchit and Vedant')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
reader = PdfReader(str(OUT))
assert len(reader.pages) == 4, f'Unexpected page count: {len(reader.pages)}'
assert all(page.extract_text().strip() for page in reader.pages)

lines = ['# Fresh verification: SignIR-Check', '',
         'Date: 2026-10-10 (America/Los_Angeles). Package 0.1.0.', '',
         'The existing product code was tested without modifications. This report is a new run, not a summary of cached results.', '',
         '## Outcomes', '',
         '- Existing suite: 25 passed, zero failures/errors (14 core, 9 workflow, 2 CLI).',
         '- Controlled evaluation: 20/20 primary errors detected; 160/160 expected statuses; 20 UNKNOWN results; 87.5% check coverage.',
         '- Authored fixture gold: 320/320 side/check values agreed. This is not independent natural-ASL validation.',
         '- Natural audit: all five checks UNKNOWN for all 643 pairs; no independent gold available.',
         '- Baseline parity: 647 comparisons, zero differences from the recovered earlier Sign F1 functions.',
         '- Four deliberate invalid runs were rejected as expected (exit 2).',
         '- Both correction examples used one saved response; the intended entity regression was recorded.',
         '- Installed package smoke passed; its 12 module hashes equal source. Original corpus inputs and source were unchanged.', '',
         '## How the existing tests work', '',
         'Core tests exercise actual extraction and comparison functions against literal expected statuses, values and evidence offsets. They include missing markers, wrong-action negation, attached counts, role reversal, unsupported inputs and repetition.', '',
         'Workflow tests cover connected duplicate/document/variant groups, invalid splits/IDs, exact corpus joins and ambiguous joins, baseline edge cases, reporting denominators, dev-only calibration, frozen input rejection, and exactly one correction call.', '',
         'CLI tests launch real command-line processes and check produced records for the complete workflow. They do not validate all possible inputs. No stress test, exhaustive proof, GPU test or human ASL judgment was performed.', '',
         '## Fresh rerun method', '',
         'Synthetic examples were regenerated and prepared. Their SHA-256 exactly matched the original frozen data. The original freeze was reused, including its original development-selected thresholds; only its 32 test rows were evaluated.', '',
         'Independent safeguard probes used copies: one extra input newline, a changed stored rule signature, a changed Sign F1 threshold, and identical English split across dev/test. Each was expected to exit 2 and was checked for that result.', '',
         'Natural outputs were imported again from the single selected prior run, grouped and audited. Corpus text and detailed natural diagnostics remain in private/verification-2026-10-10/. This public folder contains only safe natural aggregates and synthetic data.', '',
         '## Interpretation', '',
         'The program is a working research foundation for evaluating improved readers. It is not yet a validated natural-gloss checker. Raw word F1 detected all 20 controlled errors too, so no detection advantage over that baseline is claimed. UNKNOWN is a legitimate abstention, not a verified match or error.', '',
         '## Commands and logs', '',
         'Run from D:/gitgit/signir. Commands below use the existing .venv interpreter. Logged destinations are this dated verification folder; freeze files are not overwritten. Private data access is needed for the natural audit and old-baseline parity command.', '']
for command in V['commands']:
    lines += [f'### {command["label"]}', '',
              f'Expected exit: {command["expected_exit_code"]}. Observed exit: {command["exit_code"]}.', '',
              '```text', '.venv/Scripts/python.exe ' + ' '.join(json.dumps(a) if ' ' in a or '"' in a else a for a in command['args']),
              '```', '', f'Log: [{command["log"]}]({command["log"]})', '']
lines += ['## Evidence files', '',
          '- `verification.json`: summary, environment, commands and integrity hashes.',
          '- `evaluation/report.json` and CSVs: controlled results, separate cohorts and denominators.',
          '- `evaluation/records.jsonl`: both fact records and supporting evidence for synthetic test cases.',
          '- `natural-summary.json`: aggregate-only natural audit.',
          '- `baseline-parity.json`: exact prior-metric compatibility results.',
          '- `correction/records.jsonl`: before/after outputs and checker transitions.',
          '- `guards/`: deliberately invalid synthetic test copies; do not treat as evaluation inputs.', '',
          'PDF: ../../output/pdf/signir-check-test-report-2026-10-10.pdf', '']
(HERE/'README.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'pdf': str(OUT), 'pages': len(reader.pages), 'methods': str(HERE/'README.md')}))
