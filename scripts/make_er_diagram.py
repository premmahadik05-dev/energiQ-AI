"""Generate the Mermaid ER diagram from the real SQLAlchemy models so documentation cannot drift from the schema."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import models  # noqa: E402,F401
from backend.app.db import Base  # noqa: E402


def mermaid() -> str:
    out = ["erDiagram"]
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        out.append(f"    {table.name} {{")
        fk_cols = {c.name for c in table.columns if c.foreign_keys}
        for col in table.columns:
            kind = str(col.type).split("(")[0].replace(" ", "_") or "TEXT"
            tags = [t for t, on in (("PK", col.primary_key), ("FK", col.name in fk_cols), ("UK", bool(col.unique))) if on]
            out.append(f"        {kind} {col.name}" + (f" {','.join(tags)}" if tags else ""))
        out.append("    }")
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        for col in table.columns:
            for fk in col.foreign_keys:
                parent = fk.column.table.name
                out.append(f'    {parent} ||--o{{ {table.name} : "{col.name}"')
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "docs" / "diagrams" / "er_diagram.mmd"
    target.write_text(mermaid(), encoding="utf-8")
    print(f"wrote {target}")
