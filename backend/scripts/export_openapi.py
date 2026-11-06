"""Export contracts/openapi.json from the FastAPI app."""
import json
import os
from pathlib import Path

os.environ.setdefault("AUTO_BOOTSTRAP", "false")
os.environ.setdefault("RUN_BACKGROUND_LOOPS", "false")

from app.main import app  # noqa: E402

out = Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print("wrote", out, "-", len(app.openapi()["paths"]), "paths")
