import base64
import json
import logging
import re
from typing import Any

from app.config import settings
from app.services.code_executor import execute_python

logger = logging.getLogger(__name__)


def _quick_fix(text: str) -> str:
    """Stage 1: Fast, deterministic regex-based JSON repair (no LLM cost)."""
    text = re.sub(r',\s*([\]}])', r'\1', text)

    quote_count = len(re.findall(r'(?<!\\)"', text))
    if quote_count % 2 != 0:
        text += '"'

    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    text += ']' * max(open_brackets, 0)
    text += '}' * max(open_braces, 0)

    return text


_LLM_REPAIR_PROMPT = """\
Du bist ein JSON-Reparatur-Experte. Du bekommst einen kaputten JSON-Text und \
die zugehoerige Fehlermeldung. Deine Aufgabe: Schreibe ausfuehrbaren Python-Code, \
der die Variable `raw` (bereits als String vorhanden, Base64-dekodiert) repariert \
und das Ergebnis mit `print(json.dumps(result, ensure_ascii=False))` ausgibt.

Regeln:
- Antworte NUR mit ausfuehrbarem Python-Code, KEIN Markdown, KEINE Erklaerungen.
- `raw` ist bereits definiert — importiere es nicht, weise es nicht neu zu.
- Importiere nur `json` und `re` (andere Module sind nicht verfuegbar).
- Der Code MUSS `print(json.dumps(...))` am Ende aufrufen.
- Wenn die Reparatur nicht moeglich ist, gib `print("REPAIR_FAILED")` aus.

Fehlermeldung:
{error_msg}

Kaputtes JSON (ggf. gekuerzt):
```
{broken_snippet}
```
"""

_LLM_REPAIR_CODE_WRAPPER = """\
import base64, json, re

raw = base64.b64decode("{b64}").decode("utf-8")

{generated_code}
"""


async def _llm_repair(broken_json: str, error_msg: str) -> str | None:
    """Stage 2: Ask Claude to generate problem-specific Python repair code.

    Returns the generated Python code string, or None on failure.
    """
    snippet = broken_json[:2000]

    prompt = _LLM_REPAIR_PROMPT.format(
        error_msg=error_msg,
        broken_snippet=snippet,
    )

    try:
        import litellm
        resp = await litellm.acompletion(
            model="anthropic/claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            api_key=settings.anthropic_api_key,
        )
        generated_code = resp.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM call for JSON repair failed")
        return None

    lines = generated_code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    generated_code = "\n".join(lines)

    if not generated_code.strip():
        logger.warning("LLM returned empty repair code")
        return None

    return generated_code


async def repair_json(broken_json: str) -> dict[str, Any] | None:
    """Attempt to repair broken JSON using a two-stage approach.

    Stage 1: Fast local regex fix (trailing commas, unclosed strings/brackets).
    Stage 2: LLM generates problem-specific Python code, executed in sandbox.

    Returns the parsed dict on success, or None if repair fails.
    """
    # --- Stage 1: quick local fix ---
    try:
        return json.loads(_quick_fix(broken_json))
    except json.JSONDecodeError as exc:
        stage1_error = str(exc)
        logger.debug("Stage 1 (quick fix) failed, falling back to LLM repair")

    # --- Stage 2: LLM-generated repair code in sandboxed executor ---
    generated_code = await _llm_repair(broken_json, stage1_error)
    if generated_code is None:
        return None

    b64 = base64.b64encode(broken_json.encode("utf-8")).decode("ascii")
    code = _LLM_REPAIR_CODE_WRAPPER.format(b64=b64, generated_code=generated_code)

    result = await execute_python(code)

    if result.get("error"):
        logger.warning("Code executor error during JSON repair: %s", result["error"])
        return None

    stdout = result.get("stdout", "").strip()

    if not stdout or stdout.startswith("REPAIR_FAILED"):
        logger.warning("JSON repair unsuccessful: %s", stdout)
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        logger.warning("Could not parse repaired JSON output: %s", stdout[:300])
        return None
