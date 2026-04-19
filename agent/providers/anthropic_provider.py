"""
agent/providers/anthropic_provider.py

Provider Anthropic via anthropic.AsyncAnthropic.
Modelo default: claude-sonnet-4-6
"""

import json
import logging

from anthropic import AsyncAnthropic
from anthropic.types import (
    Message,
    TextBlock,
    ToolUseBlock,
    ToolResultBlockParam,
)

from .base import LLMProvider, LLMResponse, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)

_FALLBACK = "Oi! Tive uma instabilidade aqui. Pode repetir sua mensagem?"


def _tool_def_to_anthropic(tool: ToolDefinition) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
    }


def _messages_to_anthropic(messages: list[dict]) -> list[dict]:
    """
    Converte lista interna de messages para formato Anthropic.

    Roles suportados:
      user       -> user
      assistant  -> assistant (pode conter tool_use blocks)
      tool       -> user com tool_result block
    """
    result: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")

        if role == "tool":
            result.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }
                ],
            })
            continue

        if role == "assistant" and msg.get("tool_calls"):
            content_blocks: list[dict] = []
            if msg.get("content"):
                content_blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            result.append({"role": "assistant", "content": content_blocks})
            continue

        result.append({
            "role": "user" if role == "user" else "assistant",
            "content": msg.get("content", "") or "",
        })

    return result


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model or "claude-sonnet-4-6"

    async def generate(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        try:
            anthropic_tools = [_tool_def_to_anthropic(t) for t in tools] if tools else []
            anthropic_messages = _messages_to_anthropic(messages)

            kwargs: dict = {
                "model": self._model,
                "max_tokens": 1024,
                "system": system,
                "messages": anthropic_messages,
            }
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            response: Message = await self._client.messages.create(**kwargs)

            stop_reason = response.stop_reason  # "end_turn" | "tool_use" | "max_tokens"

            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []

            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )
                    )
                elif isinstance(block, TextBlock):
                    if block.text:
                        text_parts.append(block.text)

            text = "".join(text_parts).strip()

            if tool_calls:
                return LLMResponse(
                    content=text,
                    tool_calls=tool_calls,
                    finish_reason="tool_use",
                )

            if not text:
                logger.warning("anthropic: stop_reason=%s mas texto vazio", stop_reason)
                return LLMResponse(content=_FALLBACK, finish_reason="error")

            return LLMResponse(content=text, finish_reason="stop")

        except Exception as exc:
            logger.error("anthropic generate erro: %s", exc, exc_info=True)
            return LLMResponse(content=_FALLBACK, finish_reason="error")

    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }
