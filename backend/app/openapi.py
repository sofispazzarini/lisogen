"""`python -m app.openapi > openapi.json`: exporta el esquema OpenAPI, fuente del cliente
tipado del front."""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True))
