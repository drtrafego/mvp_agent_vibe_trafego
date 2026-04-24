"""
agent/providers/gemini.py

Provider Gemini via google-genai (SDK novo).
Modelo default: gemini-2.5-flash

Thinking desabilitado (thinking_budget=0) para simplificar: sem thought_signature,
nosso histórico pode serializar/deserializar tool calls como strings sem perder estado.
"""

import logging
from typing import Any

from google import genai
from google.genai import types

from .base import LLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)

_FALLBACK = "Oi! Tive uma instabilidade aqui. Pode repetir sua mensagem?"


def _json_schema_to_gemini(schema: dict) -> types.Schema:
    type_map = {
        "string": types.Type.STRING,
        "number": types.Type.NUMBER,
        "integer": types.Type.INTEGER,
        "boolean": types.Type.BOOLEAN,
        "array": types.Type.ARRAY,
        "object": types.Type.OBJECT,
    }

    if schema.get("type") == "object":
        props = {}
        for name, prop in schema.get("properties", {}).items():
            props[name] = types.Schema(
                type=type_map.get(prop.get("type", "string"), types.Type.STRING),
                description=prop.get("description", ""),
            )
        return types.Schema(
            type=types.Type.OBJECT,
            properties=props or None,
            required=schema.get("required", []) or None,
        )

    return types.Schema(
        type=type_map.get(schema.get("type", "string"), types.Type.STRING),
        description=schema.get("description", ""),
    )


def _tool_def_to_gemini(tool: ToolDefinition) -> types.Tool:
    fn_decl = types.FunctionDeclaration(
        name=tool.name,
        description=tool.description,
        parameters=_json_schema_to_gemini(tool.parameters) if tool.parameters.get("properties") else None,
    )
    return types.Tool(function_declarations=[fn_decl])


def _messages_to_contents(messages: list[dict]) -> list[types.Content]:
    """
    Converte lista [{role, content, tool_calls?, ...}] para Contents do Gemini.
      user       -> user
      assistant  -> model
      tool       -> user (com FunctionResponse)
    """
    contents: list[types.Content] = []

    for msg in messages:
        role = msg.get("role", "user")

        if role == "tool":
            fn_resp = types.Part.from_function_response(
                name=msg.get("name", ""),
                response={"result": msg.get("content", "")},
            )
            contents.append(types.Content(role="user", parts=[fn_resp]))
            continue

        if role == "assistant" and msg.get("tool_calls"):
            parts: list[types.Part] = []
            if msg.get("content"):
                parts.append(types.Part.from_text(text=msg["content"]))
            for tc in msg["tool_calls"]:
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=tc.name,
                            args=tc.arguments,
                        )
                    )
                )
            contents.append(types.Content(role="model", parts=parts))
            continue

        gemini_role = "model" if role == "assistant" else "user"
        text = msg.get("content", "") or ""
        contents.append(
            types.Content(role=gemini_role, parts=[types.Part.from_text(text=text)])
        )

    return contents


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model or "gemini-2.5-flash"

    async def generate(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        try:
            gemini_tools = [_tool_def_to_gemini(t) for t in tools] if tools else None
            contents = _messages_to_contents(messages)

            config = types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.7,
                max_output_tokens=1024,
                tools=gemini_tools,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )

            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=config,
            )

            if not response.candidates:
                logger.warning("gemini: sem candidates na resposta")
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            candidate = response.candidates[0]
            finish = candidate.finish_reason

            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []

            for part in candidate.content.parts or []:
                if getattr(part, "thought", False):
                    continue
                if part.function_call and part.function_call.name:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    tc_id = f"gemini_{fc.name}_{len(tool_calls)}"
                    tool_calls.append(ToolCall(id=tc_id, name=fc.name, arguments=args))
                elif part.text:
                    text_parts.append(part.text)

            text = "".join(text_parts).strip()

            if tool_calls:
                return LLMResponse(
                    content=text,
                    tool_calls=tool_calls,
                    finish_reason="tool_use",
                )

            if not text:
                logger.warning("gemini: finish_reason=%s mas texto vazio", finish)
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            return LLMResponse(content=text, finish_reason="stop")

        except Exception as exc:
            logger.error("gemini generate erro: %s", exc, exc_info=True)
            return LLMResponse(content=_FALLBACK, finish_reason="error")

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }
