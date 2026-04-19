from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str                          # texto final (vazio se tool_calls presente)
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"           # "stop" | "tool_use" | "error"


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        system: str,
        messages: list[dict],  # [{role, content}]
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        """Chama o LLM e retorna resposta ou tool calls."""

    @abstractmethod
    def tool_result_message(self, tool_call_id: str, name: str, content: str) -> dict:
        """Formata resultado de tool no formato correto do provider."""
