import base64
import glob
import os
import subprocess
import sys

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

_OUTPUT_DIR = "/tmp/code-output"


class ExecuteRequest(BaseModel):
    code: str
    timeout: float = 30.0
    context_data: str | None = None


class FileOutput(BaseModel):
    filename: str
    content_base64: str
    mime_type: str


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    error: str | None = None
    files: list[FileOutput] = []


_MIME_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


def _collect_output_files() -> list[FileOutput]:
    files: list[FileOutput] = []
    for path in glob.glob(os.path.join(_OUTPUT_DIR, "*")):
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        mime = _MIME_TYPES.get(ext, "application/octet-stream")
        try:
            with open(path, "rb") as f:
                data = f.read(5_000_000)
            files.append(FileOutput(
                filename=os.path.basename(path),
                content_base64=base64.b64encode(data).decode(),
                mime_type=mime,
            ))
        finally:
            os.unlink(path)
    return files


def _clear_output_dir() -> None:
    for path in glob.glob(os.path.join(_OUTPUT_DIR, "*")):
        try:
            os.unlink(path)
        except OSError:
            pass


@app.post("/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest) -> ExecuteResponse:
    _clear_output_dir()

    preamble = (
        "import sys, os\n"
        f"OUTPUT_DIR = {_OUTPUT_DIR!r}\n"
    )
    if request.context_data:
        preamble += (
            "import json as _json\n"
            f"CONTEXT_DATA = _json.loads({request.context_data!r})\n"
        )

    full_code = preamble + request.code

    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=request.timeout,
        )
        files = _collect_output_files()
        return ExecuteResponse(
            stdout=result.stdout[:50_000],
            stderr=result.stderr[:5_000],
            files=files,
        )
    except subprocess.TimeoutExpired:
        _clear_output_dir()
        return ExecuteResponse(
            stdout="",
            stderr="",
            error=f"Timeout after {request.timeout}s",
        )
    except Exception as e:
        _clear_output_dir()
        return ExecuteResponse(stdout="", stderr="", error=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
