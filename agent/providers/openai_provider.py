"""
agent/providers/openai_provider.py

Provider OpenAI via openai.AsyncOpenAI.
Modelo default: gpt-4o-mini
"""

import json
import logging

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from .base import LLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)

_FALLBACK = "Oi! Tive uma instabilidade aqui. Pode repetir sua mensagem?"


def _tool_def_to_openai(tool: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """
    Converte lista interna para formato OpenAI.

    Roles suportados:
      user       -> user
      assistant  -> assistant (pode conter tool_calls)
      tool       -> tool (com tool_call_id)
    """
    result: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")

        if role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": msg.get("content", ""),
            })
            continue

        if role == "assistant" and msg.get("tool_calls"):
            openai_tool_calls = []
            for tc in msg["tool_calls"]:
                openai_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                })
            assistant_msg: dict = {
                "role": "assistant",
                "tool_calls": openai_tool_calls,
            }
            if msg.get("content"):
                assistant_msg["content"] = msg["content"]
            result.append(assistant_msg)
            continue

        result.append({
            "role": "user" if role == "user" else "assistant",
            "content": msg.get("content", "") or "",
        })

    return result


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model or "gpt-4o-mini"

    async def generate(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        try:
            openai_tools = [_tool_def_to_openai(t) for t in tools] if tools else []
            openai_messages = [{"role": "system", "content": system}] + _messages_to_openai(messages)

            kwargs: dict = {
                "model": self._model,
                "max_tokens": 1024,
                "temperature": 0.7,
                "messages": openai_messages,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            response: ChatCompletion = await self._client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            finish_reason = choice.finish_reason  # "stop" | "tool_calls" | "length"
            message = choice.message

            tool_calls: list[ToolCall] = []

            if message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args,
                        )
                    )

            text = (message.content or "").strip()

            if tool_calls:
                return LLMResponse(
                    content=text,
                    tool_calls=tool_calls,
                    finish_reason="tool_use",
                )

            if not text:
                logger.warning("openai: finish_reason=%s mas texto vazio", finish_reason)
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            return LLMResponse(content=text, finish_reason="stop")

        except Exception as exc:
            logger.error("openai generate erro: %s", exc, exc_info=True)
            return LLMResponse(content=_FALLBACK, finish_reason="error")

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }
