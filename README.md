# mvp_agent_vibe

Agente SDR de WhatsApp construído em Python puro com arquitetura limpa, substituindo o workflow n8n atualmente em produção. O sistema recebe mensagens via webhook Meta, processa com um LLM configurável (Claude, Gemini ou qualquer provider OpenAI-compatible), executa tools nativas (RAG, CRM, Google Calendar, notificações) e responde ao lead via o endpoint bot-send já existente no frontend Next.js.

---

## O que resolve

O workflow n8n em produção apresenta limitações estruturais que travam o crescimento do agente:

- **Travamentos e race conditions:** mensagens simultâneas do mesmo lead chegam ao n8n sem controle de fila, causando respostas duplicadas ou processamento fora de ordem.
- **LLM engessada:** trocar de modelo exige reconfigurar nodes manualmente no n8n; não há abstração de provider.
- **Sem controle de código:** toda lógica fica em JSON do n8n. Não há testes, sem versionamento real, sem debugging estruturado.
- **Escalabilidade limitada:** adicionar tools, ajustar prompts ou mudar comportamento exige navegar em interfaces visuais e redeployar workflows inteiros.

Este projeto resolve tudo isso com uma base de código Python testável, configurável via variáveis de ambiente e deployável via Docker.

---

## Visão geral da arquitetura

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
     |-- [Chat Memory] (agente_vibe.chat_sessions via asyncpg + Redis cache)
     |-- [Orquestrador LLM]
     |       |-- [SDR Agent com tools:]
     |       |       |-- rag_tool        (Supabase pgvector, schema public)
     |       |       |-- calendar_tool   (Google Calendar API)
     |       |       |-- crm_tool        (agente_vibe.contacts via asyncpg)
     |       |       `-- notify_tool     (WhatsApp -> Gastão)
     |
     v
[bot-send]                  <- Output Layer (Next.js, mantido intacto)
     |
     v
Lead recebe resposta

[APScheduler - a cada 30min]
[Follow-up Worker] -> agente_vibe.contacts -> bot-send

[CRM Frontend Next.js]      <- Vercel (agentevibe.casaldotrafego.com)
     |-- agente_vibe.contacts (leitura/escrita via Drizzle ORM + postgres.js)
     |-- Pipeline Kanban, lista de contatos, atividades
```

### Camadas

| Camada | Responsabilidade |
|--------|-----------------|
| Ingestion | Receber e validar webhooks da Meta. Verificar assinatura HMAC. Extrair payload de texto ou áudio. |
| Queue | Publicar mensagens em filas Redis particionadas por `phone_number`. Garante processamento sequencial por lead. |
| Agent Worker | Consumir fila, resolver memória, chamar o LLM com tools, executar tool calls, montar resposta final. |
| Memory | Carregar histórico do banco, cachear sessão ativa no Redis, persistir novas mensagens ao fim de cada turno. |
| Tools | Funções Python chamadas pelo LLM: RAG, CRM, Calendar, Notify. |
| Output | Enviar resposta via POST para `agente.casaldotrafego.com/api/whatsapp/bot-send`. |
| Cron | APScheduler dentro do mesmo processo envia follow-ups automáticos a cada 30 minutos. |

---

## O que é mantido do sistema atual

| Componente | Status | Observação |
|------------|--------|------------|
| Supabase project `cfjyxdqrathzremxdkoi` | Mantido | Mesma instância, mesmas credenciais |
| Tabela `agente_vibe.contacts` | Mantido | Campos `phone`, `name`, `stage`, `followup_count`, `observacoes_sdr`, `nicho`, `last_bot_msg_at`, `last_lead_msg_at` |
| Tabela `agente_vibe.chat_sessions` | Novo | Histórico de conversa por phone; substitui `n8n_chat_*` |
| Tabela `public.documents` (RAG) | Mantido | Mesmos knowledge files, mesmo embedding model (pgvector) |
| Prompts do SDR Agent | Mantidos | Migrados para arquivos `.txt` ou variáveis de ambiente |
| Frontend Next.js (bot-send) | Intacto | `agente.casaldotrafego.com` não é tocado |
| Endpoint bot-send | Intacto | `POST /api/whatsapp/bot-send` usado exatamente como hoje |
| CRM Frontend Next.js | Novo | Vercel: `agentevibe.casaldotrafego.com`. Pipeline kanban + contatos |
| `phone_number_id` Meta | Mantido | `115216611574100` |

---

## Quick start

```bash
# 1. Clonar o repositório
git clone <repo-url> mvp_agent_vibe
cd mvp_agent_vibe

# 2. Copiar e preencher variáveis de ambiente
cp .env.example .env
# Edite .env com as credenciais do Supabase, Meta, LLM e Google Calendar

# 3. Subir os serviços
docker compose up --build

# O webhook estará disponível em http://localhost:8000/webhook
```

> Para desenvolvimento local sem Docker, consulte `docs/LOCAL_DEV.md`.

---

## Documentação detalhada

- [Arquitetura completa](docs/ARCHITECTURE.md): diagrama detalhado, fluxos, decisões de design
- `docs/LOCAL_DEV.md`: setup sem Docker, debugger, hot reload (a criar)
- `docs/TOOLS.md`: contrato de cada tool, exemplos de input/output (a criar)
- `docs/DEPLOY.md`: deploy Railway, variáveis de produção, health checks (a criar)
