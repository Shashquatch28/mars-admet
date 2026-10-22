"""Serve the built frontend from the API container (ADR-025).

In production one origin serves both: the API lives under `/api` and everything else is the
Vite bundle. A path that names a real file in the bundle gets that file; any other extensionless
path is a client route (`/predict`, `/batch`, ...) and gets `index.html` so the SPA can take over.
A missing file (`/assets/old-hash.js`) is a 404, not `index.html`: serving HTML where a script was
asked for hides the real error. Unknown `/api/...` paths are a JSON 404 and never reach the SPA.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}  # Vite hashes /assets file names
_NO_CACHE = {"Cache-Control": "no-cache"}  # index.html names the current hashes, so it must revalidate


def mount_spa(app: FastAPI, directory: Path) -> None:
    root = directory.resolve()
    index = root / "index.html"

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                headers = _IMMUTABLE if path.startswith("assets/") else _NO_CACHE
                return FileResponse(candidate, headers=headers)
            if "." in path.rsplit("/", 1)[-1]:
                raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index, headers=_NO_CACHE)
