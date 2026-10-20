"""Valide render.yaml contre le schéma officiel Render.

    python -m scripts.validate_blueprint [chemin/vers/render.yaml]
"""

import json
import os
import sys
from pathlib import Path

import yaml

SCHEMA_PATH = Path(os.environ.get("TEMP", "/tmp")) / "render_schema.json"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("render.yaml")

    if not SCHEMA_PATH.exists():
        print(f"Schéma absent : {SCHEMA_PATH}")
        print("Téléchargez-le : https://render.com/schema/render.yaml.json")
        return 2

    spec = yaml.safe_load(target.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    try:
        import jsonschema
    except ImportError:
        print("jsonschema absent : pip install jsonschema")
        return 2

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))

    if not errors:
        print(f"✅ {target} valide selon le schéma Render officiel.")
        print(f"   services   : {[s['name'] for s in spec['services']]}")
        print(f"   databases  : {[d['name'] for d in spec['databases']]}")
        return 0

    print(f"❌ {len(errors)} erreur(s) de validation :")
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "(racine)"
        print(f"   - [{path}] {e.message[:160]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
