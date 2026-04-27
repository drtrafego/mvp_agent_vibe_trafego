"""
agent/core.py

Nucleo do agente SDR: system prompt, definicao de tools e loop de tool calling.
"""

import logging

from .providers.base import ToolDefinition, ToolCall
from .providers.factory import get_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt completo da Claudia
# ---------------------------------------------------------------------------

SDR_SYSTEM_PROMPT = """Você é Claudia, SDR do Agente 24 Horas. Conversa com leads no WhatsApp, descobre o negócio, mostra como um agente de IA ajuda, e agenda call de 30 min com o Gastão.

ESTILO: texto curto, 1-2 frases, sem asterisco, sem travessão, português com acentos. Conversa humana, não pitch.

FLUXO:
1. Lead chega → 1 pergunta curta sobre o que ele faz.
2. Descobriu nicho → consulte RAG (search_knowledge) com o nicho e entregue 1 dado de impacto em 1 frase: "Clinicas como a sua perdem 3-5 pacientes/semana...". Pergunte se bate.
3. Confirmou a dor → proponha call e peça email na mesma mensagem: "[Nome], faz sentido 30 min com o Gastão. Me passa seu email que eu verifico os horários."
4. Recebeu email → chame get_calendar_slots, apresente os 3 horários numerados.
5. Lead escolheu → chame create_calendar_event (nome, email, ISO -03:00, título "Call Agente 24 Horas - Gastão x [nome]"). Confirma: "Pronto [nome], o convite caiu no seu email."
6. Atualize CRM com update_lead_profile sempre que descobrir info: nicho/stage/temperature.

REGRAS:
- Use search_knowledge antes de falar de preço, objeção (chatbot, robô, LGPD), case, integração.
- Quando lead pergunta preço sem valor construído: "ótima pergunta, antes me conta..." (RAG da virada de preço).
- Se RAG vazia: "vou pedir pro Gastão te explicar na call com números reais". Nunca invente.
- Lead diz não tem interesse 2x → "Entendido, obrigada pelo seu tempo. Sucesso!" e para.
- Nunca se reapresenta se já se apresentou. Use nome do lead desde a primeira fala.
- Nunca confirma agendamento sem criar evento. Nunca cria sem nome+email.

TOOLS:
- search_knowledge(query): RAG produto/nicho/objeção/preço.
- get_calendar_slots(): 3 horários disponíveis.
- create_calendar_event(name, email, iso_datetime, title): cria evento (já marca stage=agendado).
- update_lead_profile(nicho, stage, temperature): qualificando/interesse/sem_interesse + cold/warm/hot.

SAÍDA: sempre produza uma resposta pro lead. Nunca vazia."""

# ---------------------------------------------------------------------------
# Definicao das tools expostas ao LLM
# ---------------------------------------------------------------------------

TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="search_knowledge",
        description=(
            "Busca na base de conhecimento RAG sobre produto, nichos, objeções, preços, cases. "
            "Use ANTES de responder sobre qualquer desses tópicos."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto de busca relevante para o contexto da conversa"},
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="get_calendar_slots",
        description=(
            "Busca 3 horários disponíveis nos próximos dias úteis. "
            "Use quando o lead aceitou a call e passou o email."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    ToolDefinition(
        name="create_calendar_event",
        description=(
            "Cria evento no Google Calendar. "
            "Use SOMENTE após o lead confirmar o horário E passar o email."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome completo do lead"},
                "email": {"type": "string", "description": "Email do lead"},
                "iso_datetime": {
                    "type": "string",
                    "description": "Data e hora em ISO 8601 com fuso -03:00, ex: 2026-04-17T10:00:00-03:00",
                },
                "title": {"type": "string", "description": "Título do evento"},
            },
            "required": ["name", "email", "iso_datetime", "title"],
        },
    ),
    ToolDefinition(
        name="update_lead_profile",
        description=(
            "Atualiza o perfil do lead no CRM. Use sempre que descobrir uma informação relevante.\n"
            "Quando chamar:\n"
            "- Descobriu o nicho/segmento → passe nicho + stage='qualificando' + temperature='warm'.\n"
            "- Lead se mostrou interessado, fez perguntas detalhadas ou aceitou ouvir sobre a call → stage='interesse' + temperature='hot'.\n"
            "- Lead recusou explicitamente, disse que não tem interesse, pediu para tirar do contato → stage='sem_interesse'.\n"
            "Não precisa chamar quando agenda (criar evento já marca stage=agendado automaticamente)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nicho": {"type": "string", "description": "Nicho/segmento do lead, ex: clinica medica, imobiliaria, e-commerce"},
                "stage": {"type": "string", "description": "Stage CRM: qualificando, interesse, sem_interesse"},
                "temperature": {"type": "string", "description": "Temperatura: cold, warm, hot"},
            },
            "required": [],
        },
    ),
]

# ---------------------------------------------------------------------------
# Executor de tools
# ---------------------------------------------------------------------------

_FALLBACK_TOOL = "Ferramenta indisponível no momento."


async def execute_tool(name: str, args: dict, phone: str) -> str:
    """Executa a tool pelo nome e retorna resultado como string. Lazy imports."""
    try:
        if name == "search_knowledge":
            from tools.rag import search_knowledge
            return await search_knowledge(args["query"])

        if name == "get_contact_info":
            from tools.crm import get_contact
            contact = await get_contact(phone)
            return str(contact)

        if name == "save_observation":
            from tools.crm import append_observation
            await append_observation(phone, args["observation"])
            return "Observação salva."

        if name == "update_lead_profile":
            from tools.crm import update_lead_profile
            await update_lead_profile(
                phone,
                nicho=args.get("nicho"),
                stage=args.get("stage"),
                temperature=args.get("temperature"),
            )
            return "Perfil atualizado."

        if name == "get_calendar_slots":
            from tools.calendar import get_available_slots
            return await get_available_slots()

        if name == "create_calendar_event":
            from tools.calendar import create_event
            from tools.crm import advance_stage, update_contact
            from tools.notify import notify_appointment
            event = await create_event(
                name=args["name"],
                email=args["email"],
                iso_datetime=args["iso_datetime"],
                title=args["title"],
            )
            # Marca lead como agendado (exclui de follow-ups futuros)
            try:
                await advance_stage(phone, "agendado")
                await update_contact(phone, name=args["name"], email=args["email"])
            except Exception as exc:
                logger.error("Falha ao atualizar stage/contact após agendamento: %s", exc)
            await notify_appointment(event)
            return f"Evento criado: {event.get('htmlLink', 'sem link')}"

        logger.warning("execute_tool: tool desconhecida '%s'", name)
        return f"Tool {name} não encontrada."

    except KeyError as exc:
        logger.error("execute_tool '%s': argumento faltando: %s", name, exc)
        return f"Erro: argumento obrigatório ausente ({exc})."
    except Exception as exc:
        logger.error("execute_tool '%s' erro: %s", name, exc, exc_info=True)
        return _FALLBACK_TOOL


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

_FALLBACK_RESPONSE = "Oi! Tive uma instabilidade aqui. Pode repetir sua mensagem?"
_MAX_ITERATIONS = 3
_HISTORY_LIMIT = 10  # ultimas N mensagens enviadas ao LLM


async def process_message(phone: str, text: str) -> str:
    """
    Processa mensagem do lead e retorna resposta do agente.

    Loop: LLM -> tool calls -> resultados -> LLM -> ... -> resposta final.
    Maximo de _MAX_ITERATIONS iteracoes para evitar loop infinito.
    """
    from memory.chat import get_history

    provider = get_provider()
    history = await get_history(phone)

    # Limita historico para reduzir tokens enviados ao LLM
    if len(history) > _HISTORY_LIMIT:
        history = history[-_HISTORY_LIMIT:]

    # Monta contexto com mensagem atual
    messages: list[dict] = history + [{"role": "user", "content": text}]

    for iteration in range(_MAX_ITERATIONS):
        logger.debug("process_message: iteracao %d/%d para %s", iteration + 1, _MAX_ITERATIONS, phone)

        response = await provider.generate(
            system=SDR_SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        # Erro ou resposta completamente vazia
        if response.finish_reason == "error" or (not response.content and not response.tool_calls):
            logger.warning("process_message: resposta invalida na iteracao %d", iteration + 1)
            return _FALLBACK_RESPONSE

        # Resposta final sem tool calls
        if not response.tool_calls:
            return response.content or _FALLBACK_RESPONSE

        # Tem tool calls: adiciona turno do assistant e processa cada tool
        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": response.tool_calls,
        })

        for tc in response.tool_calls:
            logger.debug("process_message: executando tool '%s' args=%s", tc.name, tc.arguments)
            result = await execute_tool(tc.name, tc.arguments, phone)
            tool_msg = provider.tool_result_message(tc.id, tc.name, result)
            messages.append(tool_msg)

    # Fallback apos esgotar iteracoes
    logger.error("process_message: limite de %d iteracoes atingido para %s", _MAX_ITERATIONS, phone)
    return "Deixa eu verificar isso e já te respondo."
