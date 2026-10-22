"""Print the OpenAPI schema (no database needed). CI diffs it against the committed copy so a
contract change cannot land without the frontend regenerating its types.

    python -m zolo.api.export_openapi > openapi.json
"""

import json
import sys

from zolo.api.main import create_app
from zolo.core.config import Settings


def schema() -> dict[str, object]:
    # Placeholder values: the schema does not depend on them and nothing connects.
    # demo_mode=True so the documented contract includes the demo-only endpoints too.
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            session_secret="x" * 32,
            demo_mode=True,
            demo_token="x" * 8,
        )
    )
    return app.openapi()


if __name__ == "__main__":
    json.dump(schema(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
