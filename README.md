# mvp_agent_vibe

Agente SDR de WhatsApp construído em Python puro com arquitetura limpa, substituindo o workflow n8n atualmente em produção. O sistema recebe mensagens via webhook Meta, processa com um LLM configurável (Claude, Gemini ou qualquer provider OpenAI-compatible), executa tools nativas (RAG, CRM, Google Calendar, notificações) e responde ao lead via o endpoint bot-send já existente no frontend Next.js.

---

## O que resolve

O workflow n8n em produção apresenta limitações estruturais que travam o crescimento do agente:

- **Travamentos e race conditions:** mensagens simultâneas do mesmo lead chegam ao n8n sem controle de fila, causando respostas duplicadas ou processamento fora de ordem.
- **LLM engessada:** trocar de modelo exige reconfigurar nodes manualmente no n8n; não há abstração de provider.
- **Sem controle de codigo:** toda logica fica em JSON do n8n. Nao ha testes, sem versionamento real, sem debugging estruturado.
- **Escalabilidade limitada:** adicionar tools, ajustar prompts ou mudar comportamento exige navegar em interfaces visuais e redeployar workflows inteiros.

Este projeto resolve tudo isso com uma base de codigo Python testavel, configuravel via variaveis de ambiente e deployavel via Docker.

---

## Visao geral da arquitetura

```
Meta Webhook
     |
     v
[FastAPI /webhook]          <- Ingestion Layer
     |
     v
[Redis Queue]               <- Queue Layer (por phone_number, evita race conditions)
     |
     v
[Agent Worker]              <- Processing Layer
     |-- Audio? --> [Gemini Transcription] --> normaliza texto
     |-- [Chat Memory] (Supabase Postgres + Redis cache)
     |-- [Orquestrador LLM]
     |       |-- [SDR Agent com tools:]
     |       |       |-- rag_tool        (Supabase pgvector)
     |       |       |-- calendar_tool   (Google Calendar API)
     |       |       |-- crm_tool        (Supabase contacts)
     |       |       `-- notify_tool     (WhatsApp -> Gastao)
     |
     v
[bot-send]                  <- Output Layer (Next.js, mantido intacto)
     |
     v
Lead recebe resposta

[APScheduler - a cada 30min]
[Follow-up Worker] -> Supabase -> bot-send
```

### Camadas

| Camada | Responsabilidade |
|--------|-----------------|
| Ingestion | Receber e validar webhooks da Meta. Verificar assinatura HMAC. Extrair payload de texto ou audio. |
| Queue | Publicar mensagens em filas Redis particionadas por `phone_number`. Garante processamento sequencial por lead. |
| Agent Worker | Consumir fila, resolver memoria, chamar o LLM com tools, executar tool calls, montar resposta final. |
| Memory | Carregar historico do Supabase, cachear sessao ativa no Redis, persistir novas mensagens ao fim de cada turno. |
| Tools | Funcoes Python chamadas pelo LLM: RAG, CRM, Calendar, Notify. |
| Output | Enviar resposta via POST para `agente.casaldotrafego.com/api/whatsapp/bot-send`. |
| Cron | APScheduler dentro do mesmo processo envia follow-ups automaticos a cada 30 minutos. |

---

## O que e mantido do sistema atual

| Componente | Status | Observacao |
|------------|--------|------------|
| Supabase project `cfjyxdqrathzremxdkoi` | Mantido | Mesma instancia, mesmas credenciais |
| Tabela `contacts` (CRM) | Mantido | Schema identico, mesmos stages |
| Tabela `documents` (RAG) | Mantido | Mesmos 5 knowledge files, mesmo embedding model |
| Tabelas `n8n_chat_*` (memory) | Mantido | Leitura compativel; escrita migrada para o novo formato |
| Prompts do SDR Agent | Mantidos | Migrados para arquivos `.txt` ou variaveis de ambiente |
| Frontend Next.js | Intacto | `agente.casaldotrafego.com` nao e tocado |
| Endpoint bot-send | Intacto | `POST /api/whatsapp/bot-send` usado exatamente como hoje |
| `phone_number_id` Meta | Mantido | `115216611574100` |

---

## Quick start

```bash
# 1. Clonar o repositorio
git clone <repo-url> mvp_agent_vibe
cd mvp_agent_vibe

# 2. Copiar e preencher variaveis de ambiente
cp .env.example .env
# Edite .env com as credenciais do Supabase, Meta, LLM e Google Calendar

# 3. Subir os servicos
docker compose up --build

# O webhook estara disponivel em http://localhost:8000/webhook
```

> Para desenvolvimento local sem Docker, consulte `docs/LOCAL_DEV.md`.

---

## Documentacao detalhada

- [Arquitetura completa](docs/ARCHITECTURE.md): diagrama detalhado, fluxos, decisoes de design
- `docs/LOCAL_DEV.md`: setup sem Docker, debugger, hot reload (a criar)
- `docs/TOOLS.md`: contrato de cada tool, exemplos de input/output (a criar)
- `docs/DEPLOY.md`: deploy Railway, variaveis de producao, health checks (a criar)
