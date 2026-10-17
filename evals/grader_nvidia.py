"""Proveedor de texto para el grader factuality nativo de Promptfoo."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI
from core.llm import get_active_model, get_api_key, get_base_url


def call_api(prompt, options=None, context=None):
    try:
        messages = json.loads(prompt)
    except (ValueError, TypeError):
        messages = None
    if not isinstance(messages, list):
        messages = [{"role": "user", "content": prompt}]
    # La clave nunca se incluye en la configuración ni en el reporte.
    with OpenAI(api_key=get_api_key(), base_url=get_base_url(), timeout=120,
                max_retries=1) as client:
        response = client.chat.completions.create(
            model=get_active_model(), messages=messages, temperature=0,
        )
    content = response.choices[0].message.content
    if not content:
        return {"error": "El grader NVIDIA no devolvió contenido."}
    return {"output": content}
