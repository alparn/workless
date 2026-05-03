import json
import logging

import httpx

logger = logging.getLogger(__name__)

_CODE_RUNNER_URL = "http://code-runner:8001"


async def execute_python(
    code: str,
    timeout: float = 30.0,
    context_data: dict | list | None = None,
) -> dict:
    """Send Python code to the isolated code-runner container and return the result.

    ``context_data`` is serialised to JSON and made available inside the
    sandbox as the variable ``CONTEXT_DATA``.  The sandbox also exposes
    ``OUTPUT_DIR`` — any file written there is returned as base64.
    """
    payload: dict = {"code": code, "timeout": timeout}
    if context_data is not None:
        payload["context_data"] = json.dumps(context_data, default=str, ensure_ascii=False)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_CODE_RUNNER_URL}/execute",
                json=payload,
                timeout=timeout + 5,
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as exc:
        logger.error("Code runner unreachable: %s", exc)
        return {"stdout": "", "stderr": "", "error": f"Code runner unreachable: {exc}", "files": []}
    except httpx.HTTPStatusError as exc:
        logger.error("Code runner returned %s", exc.response.status_code)
        return {"stdout": "", "stderr": "", "error": f"Code runner error: {exc.response.status_code}", "files": []}
