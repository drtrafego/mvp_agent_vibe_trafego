from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _first_name(lead: dict) -> str:
    name = (lead.get("name") or "").strip()
    if not name:
        return "Olá"
    return name.split()[0]


def _short_obs(lead: dict) -> str:
    """Extrai primeira linha não vazia das observações como resumo."""
    obs = lead.get("observacoes_sdr", "") or ""
    for line in obs.splitlines():
        clean = line.strip()
        # Remover prefixo de timestamp como "[10:30] "
        if clean.startswith("[") and "]" in clean:
            clean = clean.split("]", 1)[-1].strip()
        if clean:
            return clean
    return "sua situação"


def get_followup_message(lead: dict) -> str | None:
    """Retorna mensagem de follow-up baseada em followup_count, nicho e observacoes.
    Retorna None se nao deve enviar mensagem."""
    count = lead.get("followup_count", 0)
    nicho = (lead.get("nicho") or "").strip()
    obs = lead.get("observacoes_sdr", "") or ""
    nome = _first_name(lead)
    has_nicho = bool(nicho)
    has_long_obs = len(obs) >= 150

    # Reagendamento: stage agendado sem show
    if count == 99:
        return (
            f"{nome}, não te vi na call com o Gastão. "
            "Aconteceu alguma coisa? Posso reagendar se quiser."
        )

    if count == 0:
        if has_nicho:
            return (
                f"Oi {nome}, vi que você trabalha com {nicho}. "
                "Surgiu alguma dúvida sobre como o agente funciona nesse segmento?"
            )
        return f"Oi {nome}, tudo bem? Ficou alguma dúvida sobre o que conversamos?"

    if count == 1:
        if has_nicho:
            return (
                f"{nome}, muita coisa no {nicho} pode ser automatizada sem complicar a operação. "
                "Faz sentido a gente conversar 30 min?"
            )
        return f"{nome}, ainda faz sentido entender como o agente funciona pro seu negócio?"

    if count == 2:
        if has_long_obs:
            obs_resumo = _short_obs(lead)
            return (
                f"{nome}, você mencionou {obs_resumo}. "
                "Se quiser entender como resolver isso, é só me falar."
            )
        return (
            f"{nome}, última tentativa de contato. "
            "Se não for o momento certo, sem problema. Só me avisa e te tiro da lista."
        )

    if count == 3:
        return (
            f"{nome}, entendo que você pode estar ocupado. "
            "Quando quiser retomar, estarei por aqui."
        )

    if count == 4:
        return (
            f"{nome}, ainda dá tempo de marcar uma conversa. "
            "Se mudar de ideia até amanhã, é só me chamar."
        )

    if count == 5:
        return f"{nome}, última mensagem da minha parte. Sucesso no seu negócio!"

    # count >= 6: nao enviar
    return None
