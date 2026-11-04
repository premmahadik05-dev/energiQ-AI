"""Convert a .docx to PDF with LibreOffice and refresh its table of contents first (a plain conversion leaves Word fields empty).

    python scripts/docx_to_pdf.py docs/academic/EnergiQ_AI_Final_Report.docx

Needs LibreOffice (`soffice`) and its Python bridge (`import uno`). Exits with a message, not a traceback, if either is missing.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1]).resolve()
    try:
        import uno  # noqa: PLC0415 - optional dependency shipped with LibreOffice
        from com.sun.star.beans import PropertyValue  # noqa: PLC0415
    except ImportError:
        print("LibreOffice's Python bridge (uno) is not available; skipping the PDF export.")
        return 1
    port = 2002
    proc = subprocess.Popen(["soffice", "--headless", "--invisible", "--norestore", f"--accept=socket,host=127.0.0.1,port={port};urp;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        ctx = None
        for _ in range(60):
            try:
                ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                break
            except Exception:  # noqa: BLE001 - the office process is still starting
                time.sleep(1)
        if ctx is None:
            print("could not connect to LibreOffice")
            return 1
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

        def prop(name, value):
            p = PropertyValue()
            p.Name, p.Value = name, value
            return p

        doc = desktop.loadComponentFromURL(src.as_uri(), "_blank", 0, (prop("Hidden", True),))
        indexes = doc.getDocumentIndexes()
        for i in range(indexes.getCount()):
            indexes.getByIndex(i).update()
        out = src.with_suffix(".pdf")
        doc.storeToURL(out.as_uri(), (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        print(f"wrote {out.name} ({out.stat().st_size // 1024} KB)")
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
