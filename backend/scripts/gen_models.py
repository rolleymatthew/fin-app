from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

BASE = Path("src/main/java/com/rolley/fin/entity")
OUT = Path("app/models/entities.py")

TYPE_MAP = {
    "String": "str",
    "Integer": "int",
    "int": "int",
    "Long": "int",
    "long": "int",
    "Double": "float",
    "double": "float",
    "Float": "float",
    "float": "float",
    "BigDecimal": "Decimal",
    "Boolean": "bool",
    "boolean": "bool",
    "Date": "datetime",
    "LocalDate": "dt_date",
    "LocalDateTime": "datetime",
}

CLASS_RE = re.compile(r"\bclass\s+(\w+)")
DOCUMENT_RE = re.compile(r"@Document\((?:value=)?\"([^\"]+)\"\)")
FIELD_RE = re.compile(r"\b(private|public)\s+(static\s+)?([\w<>., ?]+)\s+(\w+)\s*;")


def java_type_to_py(t: str) -> str:
    t = t.strip()
    if t.startswith("List<") and t.endswith(">"):
        inner = t[5:-1].strip()
        return f"list[{java_type_to_py(inner)}]"
    if t.startswith("Map<") and t.endswith(">"):
        inner = t[4:-1]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) == 2:
            return f"dict[{java_type_to_py(parts[0])}, {java_type_to_py(parts[1])}]"
        return "dict"
    if t in TYPE_MAP:
        return TYPE_MAP[t]
    return t


def parse_file(path: Path) -> Tuple[str, str | None, List[Tuple[str, str, bool]]]:
    text = path.read_text(encoding="utf-8")
    class_match = CLASS_RE.search(text)
    if not class_match:
        return "", None, []
    class_name = class_match.group(1)
    doc_match = DOCUMENT_RE.search(text)
    collection = doc_match.group(1) if doc_match else None

    fields: List[Tuple[str, str, bool]] = []
    lines = text.splitlines()
    pending_id = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("@Id"):
            pending_id = True
            continue
        field_match = FIELD_RE.search(line)
        if not field_match:
            continue
        if field_match.group(2):
            continue
        type_str = field_match.group(3).strip()
        name = field_match.group(4).strip()
        has_id = pending_id
        pending_id = False
        fields.append((name, type_str, has_id))
    return class_name, collection, fields


def generate():
    all_files = [p for p in BASE.rglob("*.java") if "mapper" not in str(p)]
    models = []
    for path in all_files:
        class_name, collection, fields = parse_file(path)
        if not class_name:
            continue
        models.append((class_name, collection, fields))

    lines: List[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from datetime import date as dt_date, datetime")
    lines.append("from decimal import Decimal")
    lines.append("from pydantic import BaseModel, Field, ConfigDict")
    lines.append("")
    lines.append("# Generated from Java entity classes")
    lines.append("")
    lines.append("class BaseDoc(BaseModel):")
    lines.append("    model_config = ConfigDict(extra=\"allow\", populate_by_name=True)")
    lines.append("")

    for class_name, collection, fields in models:
        lines.append(f"class {class_name}(BaseDoc):")
        if collection:
            lines.append(f"    __collection__ = \"{collection}\"")
        else:
            lines.append("    __collection__ = None")
        if not fields:
            lines.append("    pass")
            lines.append("")
            continue
        for name, t, has_id in fields:
            py_t = java_type_to_py(t)
            if name == "id" or has_id:
                lines.append(f"    {name}: {py_t} | None = Field(default=None, alias=\"_id\")")
            else:
                lines.append(f"    {name}: {py_t} | None = None")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    generate()
