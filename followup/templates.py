from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _first_name(lead: dict) -> str:
    name = lead.get("name", "").strip()
    if not name:
        return "Ola"
    return name.split()[0]


def _short_obs(lead: dict) -> str:
    """Extrai primeira linha nao vazia das observacoes como resumo."""
    obs = lead.get("observacoes_sdr", "") or ""
    for line in obs.splitlines():
        clean = line.strip()
        # Remover prefixo de timestamp como "[10:30] "
        if clean.startswith("[") and "]" in clean:
            clean = clean.split("]", 1)[-1].strip()
        if clean:
            return clean
    return "sua situacao"


def get_followup_message(lead: dict) -> str | None:
    """Retorna mensagem de follow-up baseada em followup_count, nicho e observacoes.
    Retorna None se nao deve enviar mensagem."""
    count = lead.get("followup_count", 0)
    nicho = lead.get("nicho", "").strip()
    obs = lead.get("observacoes_sdr", "") or ""
    nome = _first_name(lead)
    has_nicho = bool(nicho)
    has_long_obs = len(obs) >= 150

    # Reagendamento: stage agendado sem show
    if count == 99:
        return (
            f"{nome}, nao te vi na call com o Gastao. "
            "Aconteceu alguma coisa? Posso reagendar se quiser."
        )

    if count == 0:
        if has_nicho:
            return (
                f"Oi {nome}, vi que voce trabalha com {nicho}. "
                "Surgiu alguma duvida sobre como o agente funciona nesse segmento?"
            )
        return f"Oi {nome}, tudo bem? Ficou alguma duvida sobre o que conversamos?"

    if count == 1:
        if has_nicho:
            return (
                f"{nome}, muita coisa no {nicho} pode ser automatizada sem complicar a operacao. "
                "Faz sentido a gente conversar 30 min?"
            )
        return f"{nome}, ainda faz sentido entender como o agente funciona pro seu negocio?"

    if count == 2:
        if has_long_obs:
            obs_resumo = _short_obs(lead)
            return (
                f"{nome}, voce mencionou {obs_resumo}. "
                "Se quiser entender como resolver isso, e so me falar."
            )
        return (
            f"{nome}, ultima tentativa de contato. "
            "Se nao for o momento certo, sem problema. So me avisa e te tiro da lista."
        )

    if count == 3:
        return (
            f"{nome}, entendo que voce pode estar ocupado. "
            "Quando quiser retomar, estarei por aqui."
        )

    if count == 4:
        return f"{nome}, ultima mensagem da minha parte. Sucesso no seu negocio!"

    # count >= 5: nao enviar
    return None
