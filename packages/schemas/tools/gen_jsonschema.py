#!/usr/bin/env python3
"""Erzeugt JSON Schema (Draft 2020-12) aus dem Protobuf-Descriptor-Set.

Die JSON-Schemas werden nicht von Hand gepflegt, sondern aus demselben
Descriptor-Set abgeleitet, aus dem auch der Python- und TypeScript-Code
entsteht. Damit bleibt die Regel aus Kapitel 16 des Konzepts gewahrt:
packages/schemas ist die einzige Wahrheitsquelle, alles andere wird generiert.

Die Schemas bilden die *kanonische Protobuf-JSON-Abbildung* ab, nicht eine
eigene Wunschform. Konkret:

* 64-Bit-Ganzzahlen sind Strings (Zahl wird beim Lesen ebenfalls akzeptiert).
* Enums sind Wertnamen; die Ganzzahl wird ebenfalls akzeptiert.
* google.protobuf.Timestamp ist ein RFC-3339-String in UTC.
* Jedes Feld darf null sein - das bedeutet in Protobuf-JSON "nicht gesetzt".
* Feldnamen sind sowohl in proto- als auch in lowerCamelCase-Schreibweise
  zulaessig, aber nie beide gleichzeitig im selben Dokument.

Zwei Varianten je Nachricht:

* <Name>.schema.json         - proto3-treu, keine Pflichtfelder. proto3 kennt
                               keine required-Felder; ein Schema, das welche
                               behauptet, waere eine Fiktion.
* <Name>.strict.schema.json  - zusaetzlich die Pflichtfelder aus
                               tools/required.json. Das ist die Vertragsebene
                               der Pipeline: was ein Konnektor liefern muss,
                               damit die Nachricht angenommen wird.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from google.protobuf import descriptor_pb2

FD = descriptor_pb2.FieldDescriptorProto

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# Pfadindizes in FileDescriptorProto / DescriptorProto fuer die Zuordnung von
# Kommentaren (SourceCodeInfo).
_FILE_MESSAGE = 4
_FILE_ENUM = 5
_MSG_FIELD = 2
_MSG_NESTED = 3
_MSG_ENUM = 4
_ENUM_VALUE = 2

# Kernobjekte, fuer die ein eigenes Schema-Dokument erzeugt wird.
ROOT_MESSAGES = [
    "argus.v1.Observation",
    "argus.v1.Event",
    "argus.v1.Entity",
    "argus.v1.Relation",
    "argus.v1.Report",
    "argus.v1.Track",
    "argus.v1.Assessment",
    "argus.v1.Source",
    "argus.v1.Aoi",
    "argus.v1.Watchlist",
    "argus.v1.Alert",
    "argus.v1.Case",
]

_NUMBER = {
    "anyOf": [
        {"type": "number"},
        # Protobuf-JSON erlaubt diese drei Sonderwerte als String.
        {"enum": ["NaN", "Infinity", "-Infinity"]},
    ]
}
_INT64 = {
    # Kanonisch ein String; die Ganzzahl wird beim Lesen ebenfalls akzeptiert.
    "anyOf": [{"type": "string", "pattern": r"^-?\d+$"}, {"type": "integer"}]
}

_WELL_KNOWN: dict[str, dict] = {
    ".google.protobuf.Timestamp": {
        "type": "string",
        "format": "date-time",
        "description": "RFC 3339 in UTC, z. B. 2026-08-28T09:14:03.221Z",
    },
    ".google.protobuf.Duration": {
        "type": "string",
        "pattern": r"^-?\d+(\.\d+)?s$",
        "description": "Dauer in Sekunden mit Suffix s, z. B. 1.5s",
    },
    ".google.protobuf.Struct": {
        "type": "object",
        "description": "Freies JSON-Objekt (google.protobuf.Struct)",
    },
    ".google.protobuf.Value": {
        "description": "Beliebiger JSON-Wert (google.protobuf.Value)"
    },
    ".google.protobuf.ListValue": {"type": "array"},
    ".google.protobuf.FieldMask": {"type": "string"},
    ".google.protobuf.Empty": {"type": "object", "additionalProperties": False},
    ".google.protobuf.BoolValue": {"type": "boolean"},
    ".google.protobuf.StringValue": {"type": "string"},
    ".google.protobuf.DoubleValue": _NUMBER,
    ".google.protobuf.FloatValue": _NUMBER,
    ".google.protobuf.Int32Value": {"type": "integer"},
    ".google.protobuf.UInt32Value": {"type": "integer", "minimum": 0},
    ".google.protobuf.Int64Value": _INT64,
    ".google.protobuf.UInt64Value": _INT64,
    ".google.protobuf.BytesValue": {"type": "string", "contentEncoding": "base64"},
}


def _to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


class Index:
    """Nachschlagewerk ueber alle Nachrichten, Enums und Kommentare."""

    def __init__(self, fds: descriptor_pb2.FileDescriptorSet) -> None:
        self.messages: dict[str, descriptor_pb2.DescriptorProto] = {}
        self.enums: dict[str, descriptor_pb2.EnumDescriptorProto] = {}
        self.comments: dict[str, str] = {}
        for fdp in fds.file:
            self._index_file(fdp)

    def _index_file(self, fdp: descriptor_pb2.FileDescriptorProto) -> None:
        prefix = f".{fdp.package}" if fdp.package else ""
        by_path = {
            tuple(loc.path): loc.leading_comments
            for loc in fdp.source_code_info.location
            if loc.leading_comments
        }
        for i, msg in enumerate(fdp.message_type):
            self._index_message(msg, prefix, (_FILE_MESSAGE, i), by_path)
        for i, enum in enumerate(fdp.enum_type):
            self._index_enum(enum, prefix, (_FILE_ENUM, i), by_path)

    def _index_message(self, msg, prefix, path, by_path) -> None:
        fqn = f"{prefix}.{msg.name}"
        self.messages[fqn] = msg
        self._comment(fqn, path, by_path)
        for i, field in enumerate(msg.field):
            self._comment(f"{fqn}#{field.name}", path + (_MSG_FIELD, i), by_path)
        for i, nested in enumerate(msg.nested_type):
            self._index_message(nested, fqn, path + (_MSG_NESTED, i), by_path)
        for i, enum in enumerate(msg.enum_type):
            self._index_enum(enum, fqn, path + (_MSG_ENUM, i), by_path)

    def _index_enum(self, enum, prefix, path, by_path) -> None:
        fqn = f"{prefix}.{enum.name}"
        self.enums[fqn] = enum
        self._comment(fqn, path, by_path)
        for i, value in enumerate(enum.value):
            self._comment(f"{fqn}#{value.name}", path + (_ENUM_VALUE, i), by_path)

    def _comment(self, key: str, path: tuple, by_path: dict) -> None:
        # Schluessel ohne fuehrenden Punkt, damit sie zu den JSON-Schema-Titeln
        # passen (dort steht "argus.v1.Observation", nicht ".argus.v1...").
        key = key.lstrip(".")
        raw = by_path.get(path)
        if not raw:
            return
        text = "\n".join(line.strip() for line in raw.strip().splitlines())
        text = re.sub(r"\n{2,}", "\n\n", text).strip()
        if text:
            self.comments[key] = text


class Generator:
    def __init__(self, index: Index, required: dict[str, list[str]]) -> None:
        self.index = index
        self.required = required
        self._defs: dict[str, dict] = {}

    # -- Typabbildung ------------------------------------------------------

    def _scalar(self, field) -> dict:
        t = field.type
        if t in (FD.TYPE_DOUBLE, FD.TYPE_FLOAT):
            return dict(_NUMBER)
        if t in (FD.TYPE_INT64, FD.TYPE_SINT64, FD.TYPE_SFIXED64):
            return dict(_INT64)
        if t in (FD.TYPE_UINT64, FD.TYPE_FIXED64):
            return dict(_INT64)
        if t in (FD.TYPE_UINT32, FD.TYPE_FIXED32):
            return {"type": "integer", "minimum": 0}
        if t in (FD.TYPE_INT32, FD.TYPE_SINT32, FD.TYPE_SFIXED32):
            return {"type": "integer"}
        if t == FD.TYPE_BOOL:
            return {"type": "boolean"}
        if t == FD.TYPE_STRING:
            return {"type": "string"}
        if t == FD.TYPE_BYTES:
            return {"type": "string", "contentEncoding": "base64"}
        raise ValueError(f"unbekannter Skalartyp {t} in {field.name}")

    def _enum_schema(self, type_name: str) -> dict:
        enum = self.index.enums[type_name]
        names = [v.name for v in enum.value]
        doc = self.index.comments.get(type_name.lstrip("."), "")
        value_docs = []
        for v in enum.value:
            c = self.index.comments.get(f"{type_name.lstrip('.')}#{v.name}")
            if c:
                value_docs.append(f"{v.name}: {c}")
        parts = [p for p in (doc, "\n".join(value_docs)) if p]
        schema = {
            "anyOf": [
                {"enum": names},
                # Protobuf-JSON akzeptiert auch die Ordnungszahl.
                {"type": "integer", "enum": [v.number for v in enum.value]},
            ]
        }
        if parts:
            schema["description"] = "\n\n".join(parts)
        return schema

    def _map_entry(self, type_name: str):
        msg = self.index.messages.get(type_name)
        if msg is not None and msg.options.map_entry:
            return msg
        return None

    def _field_schema(self, field) -> dict:
        if field.type == FD.TYPE_ENUM:
            base = self._enum_schema(field.type_name)
        elif field.type == FD.TYPE_MESSAGE:
            entry = self._map_entry(field.type_name)
            if entry is not None:
                value_field = entry.field[1]
                return {
                    "type": "object",
                    "propertyNames": {"type": "string"},
                    "additionalProperties": self._field_schema(value_field),
                }
            wk = _WELL_KNOWN.get(field.type_name)
            base = dict(wk) if wk is not None else self._ref(field.type_name)
        elif field.type == FD.TYPE_GROUP:
            raise ValueError("Groups werden nicht unterstuetzt")
        else:
            base = self._scalar(field)

        if field.label == FD.LABEL_REPEATED:
            return {"type": "array", "items": base}
        return base

    def _ref(self, type_name: str) -> dict:
        fqn = type_name.lstrip(".")
        self._ensure_def(type_name)
        return {"$ref": f"#/$defs/{fqn}"}

    def _ensure_def(self, type_name: str) -> None:
        fqn = type_name.lstrip(".")
        if fqn in self._defs:
            return
        self._defs[fqn] = {}  # Platzhalter gegen Endlosrekursion
        self._defs[fqn] = self._message_schema(type_name)

    @staticmethod
    def _nullable(schema: dict) -> dict:
        """Protobuf-JSON erlaubt null fuer jedes Feld: es bedeutet 'nicht gesetzt'."""
        if "$ref" in schema:
            return {"anyOf": [schema, {"type": "null"}]}
        if "anyOf" in schema and "description" not in schema:
            return {"anyOf": list(schema["anyOf"]) + [{"type": "null"}]}
        out = dict(schema)
        if "anyOf" in out:
            out["anyOf"] = list(out["anyOf"]) + [{"type": "null"}]
            return out
        t = out.get("type")
        if t is None:
            return out  # bereits beliebig (google.protobuf.Value)
        out["type"] = [t, "null"] if isinstance(t, str) else list(t) + ["null"]
        return out

    def _message_schema(self, type_name: str) -> dict:
        fqn = type_name.lstrip(".")
        msg = self.index.messages[type_name]
        properties: dict[str, dict] = {}
        dependent: dict[str, dict] = {}

        for field in msg.field:
            schema = self._nullable(self._field_schema(field))
            doc = self.index.comments.get(f"{fqn}#{field.name}")
            if doc:
                schema = dict(schema)
                existing = schema.get("description")
                schema["description"] = f"{doc}\n\n{existing}" if existing else doc
            camel = field.json_name or _to_camel(field.name)
            properties[field.name] = schema
            if camel != field.name:
                properties[camel] = schema
                # Protobuf-JSON verbietet, dasselbe Feld zweimal zu setzen -
                # einmal in proto-, einmal in camelCase-Schreibweise.
                dependent[field.name] = {"not": {"required": [camel]}}

        schema: dict = {
            "type": "object",
            "title": fqn,
            "properties": properties,
            "additionalProperties": False,
        }
        if dependent:
            schema["dependentSchemas"] = dependent
        doc = self.index.comments.get(fqn)
        if doc:
            schema["description"] = doc
        req = self.required.get(fqn)
        if req:
            schema["x-argus-required"] = req
        return schema

    # -- Dokumente ---------------------------------------------------------

    def document(self, root: str, strict: bool) -> dict:
        self._defs = {}
        body = self._message_schema(f".{root}")
        defs = {k: v for k, v in self._defs.items() if k != root}
        doc = {
            "$schema": SCHEMA_DRAFT,
            "$id": f"https://schemas.argus.local/v1/{root}{'.strict' if strict else ''}.schema.json",
            **body,
        }
        if defs:
            doc["$defs"] = defs
        if strict:
            self._apply_required(doc)
        else:
            self._strip_required_hint(doc)
        return doc

    def _apply_required(self, doc: dict) -> None:
        def walk(node: dict) -> None:
            hint = node.pop("x-argus-required", None)
            if hint:
                present = [f for f in hint if f in node.get("properties", {})]
                if present:
                    node["required"] = present
            for sub in node.get("$defs", {}).values():
                walk(sub)

        walk(doc)
        for sub in doc.get("$defs", {}).values():
            walk(sub)

    def _strip_required_hint(self, doc: dict) -> None:
        doc.pop("x-argus-required", None)
        for sub in doc.get("$defs", {}).values():
            sub.pop("x-argus-required", None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--descriptor", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--required", type=Path, default=None)
    args = ap.parse_args()

    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString(args.descriptor.read_bytes())

    required: dict[str, list[str]] = {}
    if args.required and args.required.exists():
        required = {
            k: v
            for k, v in json.loads(args.required.read_text(encoding="utf-8")).items()
            if not k.startswith("_")
        }

    index = Index(fds)
    missing = [m for m in ROOT_MESSAGES if f".{m}" not in index.messages]
    if missing:
        print(f"Fehlende Kernobjekte im Descriptor: {missing}", file=sys.stderr)
        return 1
    unknown = [k for k in required if f".{k}" not in index.messages]
    if unknown:
        print(f"required.json verweist auf unbekannte Nachrichten: {unknown}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    written = []
    for root in ROOT_MESSAGES:
        gen = Generator(index, required)
        short = root.rsplit(".", 1)[-1]
        for strict in (False, True):
            doc = gen.document(root, strict)
            name = f"{short}.strict.schema.json" if strict else f"{short}.schema.json"
            (args.out / name).write_text(
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append(name)

    (args.out / "index.json").write_text(
        json.dumps(
            {
                "schema_bundle": "argus.v1",
                "generated_from": args.descriptor.name,
                "documents": sorted(written),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(written)} JSON-Schemas nach {args.out} geschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
