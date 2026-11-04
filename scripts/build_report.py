"""Assemble the final project report from the repository's own documents and convert it to Word with pandoc.

  python scripts/build_report.py            # writes docs/academic/EnergiQ_AI_Final_Report.md and .docx

Nothing is rewritten here: chapters are the existing documents (so the report cannot disagree with them), with their top
heading removed (the chapter title replaces it). The Mermaid source block in the architecture chapter is replaced by the rendered image.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT_MD = DOCS / "academic" / "EnergiQ_AI_Final_Report.md"
OUT_DOCX = DOCS / "academic" / "EnergiQ_AI_Final_Report.docx"

CHAPTERS = [
    ("Introduction and problem statement", "academic/02_problem_statement.md"),
    ("Objectives and outcomes", "academic/03_objectives.md"),
    ("Literature review", "academic/04_literature_review.md"),
    ("Data: inventory, quality and suitability", "01_dataset_suitability.md"),
    ("Exploratory data analysis", "04_eda_report.md"),
    ("Requirements", "02_requirements.md"),
    ("System architecture", "03_architecture.md"),
    ("Machine-learning methodology", "05_ml_methodology.md"),
    ("Forecast evaluation", "06_model_evaluation.md"),
    ("Explainability, cost and recommendations", "07_explainability_and_optimization.md"),
    ("Anomaly detection", "08_anomaly_detection.md"),
    ("Backend design and API", "09_backend_and_api.md"),
    ("Web interface", "16_frontend.md"),
    ("Security", "10_security.md"),
    ("Testing", "11_testing.md"),
    ("Deployment and operations", "12_deployment.md"),
    ("MLOps and monitoring", "14_mlops_monitoring.md"),
    ("Limitations and future scope", "13_limitations.md"),
    ("Verification matrix", "15_verification_matrix.md"),
]
FIGURES = [
    ("Use cases", "diagrams/use_case.png"), ("Data flow, level 0", "diagrams/dfd_level0.png"), ("Data flow, level 1", "diagrams/dfd_level1.png"),
    ("Entity-relationship diagram (generated from the ORM)", "diagrams/er_diagram.png"), ("Class diagram (main classes)", "diagrams/uml_class.png"),
    ("Sequence: upload, train, forecast", "diagrams/sequence_train_forecast.png"), ("Machine-learning pipeline", "diagrams/ml_pipeline.png"),
    ("AWS deployment (configuration only, not deployed)", "diagrams/deployment_aws.png"),
]
SCREENSHOTS = [
    ("Dashboard", "screenshots/09_dashboard.png"), ("Dataset detail and quality report", "screenshots/05_dataset_detail.png"),
    ("Model versions and hold-out accuracy", "screenshots/06_models.png"), ("Forecast with look-back origin", "screenshots/07_forecast.png"),
    ("Anomaly detection", "screenshots/08_anomalies.png"), ("Explainability", "screenshots/11_explain.png"),
    ("Optimisation: cheapest-window scheduler", "screenshots/15_optimize_schedule.png"), ("Benchmark results", "screenshots/16_benchmark.png"),
]


def strip_h1(md: str) -> str:
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[:i] + lines[i + 1:]).lstrip("\n")
    return md


def fix_paths(md: str, src: Path) -> str:
    def repl(m: re.Match) -> str:
        target = m.group(2)
        if target.startswith(("http", "/")):
            return m.group(0)
        return f"![{m.group(1)}]({(src.parent / target).resolve()})"
    md = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, md)
    return re.sub(r"```mermaid.*?```", f"![System architecture]({(DOCS / 'diagrams' / 'system_architecture.png').resolve()})", md, flags=re.S)


def polish_docx(path: Path) -> None:
    """A4 page, margins, page numbers, readable table columns and a table of contents that Word refreshes on opening."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document(str(path))
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21.0), Cm(29.7)
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2.2)
        p = s.footer.paragraphs[0] if s.footer.paragraphs else s.footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
            run = p.add_run()
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            run._r.append(el)
    usable = Cm(21.0 - 4.4)
    for table in doc.tables:
        ncols = len(table.columns)
        if ncols == 0:
            continue
        weight = [0.0] * ncols
        for row in table.rows:
            for j, cell in enumerate(row.cells[:ncols]):
                weight[j] += min(len(cell.text), 70) + 6          # content length, capped, plus a floor
        total = sum(weight) or 1
        for row in table.rows:
            for j, cell in enumerate(row.cells[:ncols]):
                cell.width = int(usable * weight[j] / total)
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(8.5)
        tbl_pr = table._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tbl_pr.append(layout)
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)
    doc.save(str(path))


def main() -> None:
    parts = [f"---\ntitle: \"EnergiQ AI: Cloud-Native Intelligent Energy Forecasting, Anomaly Detection and Optimisation Platform\"\n"
             f"subtitle: \"Major project report\"\nauthor: \"Uzair\"\ndate: \"{date.today():%d %B %Y}\"\n---\n"]
    abstract = strip_h1((DOCS / "academic" / "01_abstract.md").read_text(encoding="utf-8"))
    parts.append("# Abstract\n\n" + re.sub(r"^\*\*EnergiQ AI:.*?\*\*\n", "", abstract, count=1, flags=re.S | re.M) + "\n")
    for n, (title, rel) in enumerate(CHAPTERS, start=1):
        path = DOCS / rel
        if not path.exists():
            print(f"skipping missing chapter: {rel}", file=sys.stderr)
            continue
        body = fix_paths(strip_h1(path.read_text(encoding="utf-8")), path)
        parts.append(f"\n\\newpage\n\n# Chapter {n}. {title}\n\n{body}\n")
    figs = "\n\n".join(f"![{cap}]({(DOCS / rel).resolve()})" for cap, rel in FIGURES if (DOCS / rel).exists())
    parts.append(f"\n\\newpage\n\n# Appendix A. Design diagrams\n\n{figs}\n")
    shots = "\n\n".join(f"![{cap}]({(DOCS / rel).resolve()})" for cap, rel in SCREENSHOTS if (DOCS / rel).exists())
    parts.append(f"\n\\newpage\n\n# Appendix B. Screenshots of the running application\n\nTaken in Chromium against a real backend with the bundled sample dataset (`docs/screenshots/`).\n\n{shots}\n")
    parts.append("\n\\newpage\n\n# References\n\n" + strip_h1((DOCS / "references.md").read_text(encoding="utf-8")) + "\n")
    OUT_MD.write_text("\n".join(parts), encoding="utf-8")
    cmd = ["pandoc", str(OUT_MD), "-o", str(OUT_DOCX), "--toc", "--toc-depth=2", "--from", "markdown+pipe_tables+yaml_metadata_block+raw_tex",
           f"--resource-path={DOCS}:{ROOT}", "--standalone"]
    subprocess.run(cmd, check=True)
    polish_docx(OUT_DOCX)
    print(f"wrote {OUT_MD.name} ({OUT_MD.stat().st_size // 1024} KB) and {OUT_DOCX.name} ({OUT_DOCX.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
