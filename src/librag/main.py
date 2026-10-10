# Copyright (C) 2026 Theo van Oostrum
"""LibRag HTTP application."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

HOMEPAGE_HTML = """\
<!DOCTYPE html>
<html>
  <head>
    <title>LibRag</title>
  </head>
  <body>
    <h1>LibRag</h1>
  </body>
</html>
"""

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/", response_class=HTMLResponse)
def homepage() -> str:
    """Return the LibRag homepage."""
    return HOMEPAGE_HTML


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
