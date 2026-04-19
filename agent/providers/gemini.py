"""
agent/providers/gemini.py

Provider Gemini via google-generativeai.
Modelo default: gemini-2.0-flash
"""

import json
import logging
from typing import Any

import google.generativeai as genai
from google.generativeai import protos

from .base import LLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)

_FALLBACK = "Oi! Tive uma instabilidade aqui. Pode repetir sua mensagem?"


def _tool_def_to_genai(tool: ToolDefinition) -> protos.Tool:
    """Converte ToolDefinition para protos.Tool do Gemini."""
    props = tool.parameters.get("properties", {})
    required = tool.parameters.get("required", [])

    genai_props: dict[str, protos.Schema] = {}
    for prop_name, prop_schema in props.items():
        prop_type = prop_schema.get("type", "string").upper()
        type_map = {
            "STRING": protos.Type.STRING,
            "NUMBER": protos.Type.NUMBER,
            "INTEGER": protos.Type.INTEGER,
            "BOOLEAN": protos.Type.BOOLEAN,
            "ARRAY": protos.Type.ARRAY,
            "OBJECT": protos.Type.OBJECT,
        }
        genai_props[prop_name] = protos.Schema(
            type=type_map.get(prop_type, protos.Type.STRING),
            description=prop_schema.get("description", ""),
        )

    fn_decl = protos.FunctionDeclaration(
        name=tool.name,
        description=tool.description,
        parameters=protos.Schema(
            type=protos.Type.OBJECT,
            properties=genai_props,
            required=required,
        ) if genai_props else None,
    )
    return protos.Tool(function_declarations=[fn_decl])


def _messages_to_contents(messages: list[dict]) -> list[protos.Content]:
    """
    Converte lista [{role, content, tool_calls?, ...}] para Contents do Gemini.

    Mapeamento de roles:
      user       -> user
      assistant  -> model
      tool       -> user (com FunctionResponse)
    """
    contents: list[protos.Content] = []

    for msg in messages:
        role = msg.get("role", "user")

        # Mensagem de resultado de tool (gerada por tool_result_message)
        if role == "tool":
            tool_name = msg.get("name", "")
            tool_content = msg.get("content", "")
            fn_resp = protos.FunctionResponse(
                name=tool_name,
                response={"result": tool_content},
            )
            contents.append(
                protos.Content(role="user", parts=[protos.Part(function_response=fn_resp)])
            )
            continue

        # Mensagem do assistant com tool_calls pendentes
        if role == "assistant" and msg.get("tool_calls"):
            parts: list[protos.Part] = []
            if msg.get("content"):
                parts.append(protos.Part(text=msg["content"]))
            for tc in msg["tool_calls"]:
                parts.append(
                    protos.Part(
                        function_call=protos.FunctionCall(
                            name=tc.name,
                            args=tc.arguments,
                        )
                    )
                )
            contents.append(protos.Content(role="model", parts=parts))
            continue

        # Mensagem normal
        gemini_role = "model" if role == "assistant" else "user"
        text = msg.get("content", "") or ""
        contents.append(protos.Content(role=gemini_role, parts=[protos.Part(text=text)]))

    return contents


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        genai.configure(api_key=api_key)
        self._model_name = model or "gemini-2.0-flash"

    async def generate(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        try:
            genai_tools = [_tool_def_to_genai(t) for t in tools] if tools else None

            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system,
                tools=genai_tools,
            )

            contents = _messages_to_contents(messages)

            response = await model.generate_content_async(
                contents,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=1024,
                ),
            )

            # Verifica se a resposta esta vazia (finish_reason STOP com zero tokens)
            if not response.candidates:
                logger.warning("gemini: sem candidates na resposta")
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            candidate = response.candidates[0]
            finish = candidate.finish_reason

            # Extrai tool calls se houver
            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []

            for part in candidate.content.parts:
                if part.function_call and part.function_call.name:
                    fc = part.function_call
                    # args e um MapComposite; converte para dict nativo
                    args = dict(fc.args) if fc.args else {}
                    # id sintetico: gemini nao retorna id de tool call
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

            # Trata output vazio sem tool calls
            if not text:
                logger.warning("gemini: finish_reason=%s mas texto vazio", finish)
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            return LLMResponse(content=text, finish_reason="stop")

        except Exception as exc:
            logger.error("gemini generate erro: %s", exc, exc_info=True)
            return LLMResponse(content=_FALLBACK, finish_reason="error")

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        """
        Gemini espera FunctionResponse dentro de Content role=user.
        Retorna dict com marcador para _messages_to_contents reconhecer.
        """
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }
