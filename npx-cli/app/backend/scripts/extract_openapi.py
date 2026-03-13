#!/usr/bin/env python3
"""Extract OpenAPI JSON schema from FastAPI app without starting the server."""

import json
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.main import app  # noqa: E402

if __name__ == "__main__":
    schema = app.openapi()
    output = json.dumps(schema, indent=2)

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(output)
    else:
        print(output)
