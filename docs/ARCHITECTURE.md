# Arquitetura — mvp_agent_vibe

---

## Diagrama completo

```
                        +-----------------------+
                        |     Meta Platform     |
                        |  (WhatsApp Business)  |
                        +-----------+-----------+
                                    |
                          POST /webhook (HMAC)
                                    |
                        +-----------v-----------+
                        |   FastAPI Application  |
                        |   GET  /webhook        |  <- verificacao inicial Meta
                        |   POST /webhook        |  <- mensagens em producao
                        |   GET  /health         |  <- health check Railway
                        +-----------+-----------+
                                    |
                      publica { phone, payload, type }
                                    |
                   +----------------v----------------+
                   |          Redis Queue            |
                   |   chave: queue:{phone_number}   |
                   |   (lista, RPUSH / BLPOP)        |
                   +----------------+----------------+
                                    |
                   +----------------v----------------+
                   |         Agent Worker            |
                   |   (asyncio task por consumer)   |
                   |                                 |
                   |  1. BLPOP fila do lead          |
                   |  2. Resolve tipo (texto/audio)  |
                   |  3. Carrega chat memory         |
                   |  4. Chama Orquestrador LLM      |
                   |  5. Executa tool calls          |
                   |  6. Monta resposta              |
                   |  7. Persiste memory             |
                   +---+--------+--------+--------+--+
                       |        |        |        |
              +--------v-+  +---v----+ +-v------+ +v-----------+
              | rag_tool |  |calendar| |crm_tool| |notify_tool |
              | pgvector |  | _tool  | |contacts| |(WhatsApp   |
              | Supabase |  |Google  | |Supabase| | -> Gastao) |
              +----------+  +--------+ +--------+ +------------+
                                    |
                       +------------v-----------+
                       |  Audio Pipeline        |
                       |  (condicional)         |
                       |  1. Download media Meta |
                       |  2. Gemini Transcribe  |
                       |  3. Normaliza texto    |
                       +------------------------+
                                    |
                       +------------v-----------+
                       |   Chat Memory Layer    |
                       |  Redis: sessao ativa   |
                       |  Supabase: historico   |
                       +------------------------+
                                    |
                          POST bot-send
                                    |
                   +----------------v----------------+
                   |   Next.js Frontend              |
                   |   agente.casaldotrafego.com     |
                   |   /api/whatsapp/bot-send        |
                   +----------------+----------------+
                                    |
                             Lead recebe
                             mensagem WA

   +-----------------------------------------+
   |  APScheduler (mesmo processo FastAPI)   |
   |  cron: a cada 30 minutos                |
   |  Follow-up Worker:                      |
   |    1. SELECT contacts WHERE follow_up   |
   |    2. Filtra leads elegíveis            |
   |    3. POST bot-send para cada lead      |
   +-----------------------------------------+
```

---

## Descricao de cada camada

### 1. Ingestion (FastAPI)

Responsavel por receber e validar todo o trafego da Meta.

- `GET /webhook`: retorna `hub.challenge` para verificacao inicial do webhook Meta.
- `POST /webhook`: valida assinatura HMAC-SHA256 com `WEBHOOK_SECRET`. Rejeita payloads invalidos com `403`. Extrai o objeto de mensagem (texto, audio, ou outros tipos ignorados). Publica na fila Redis de forma nao-bloqueante e retorna `200 OK` imediatamente para a Meta (obrigatorio: Meta considera timeout acima de 20s como falha).
- `GET /health`: endpoint simples para health check do Railway e do Docker.

Arquivos relevantes: `app/webhook.py`, `app/main.py`.

### 2. Queue (Redis)

Isola o processamento por lead para evitar race conditions.

- Chave de fila: `queue:{phone_number}` (lista Redis).
- Publicacao: `RPUSH` pelo handler do webhook.
- Consumo: `BLPOP` com timeout pelo worker, bloqueante e eficiente.
- Cada `phone_number` tem sua propria fila, portanto mensagens do mesmo lead sao sempre processadas em ordem, mesmo com alta concorrencia.
- Mensagens de leads diferentes sao processadas em paralelo (um worker asyncio por fila ativa).

Arquivos relevantes: `app/queue.py`.

### 3. Agent Worker

Nucleo do sistema. Orquestra toda a logica de processamento de uma mensagem.

Sequencia de execucao:

1. Consome item da fila Redis via `BLPOP`.
2. Identifica o tipo: texto vai direto; audio passa pelo Audio Pipeline.
3. Carrega o historico de chat da memoria unificada.
4. Monta o contexto (historico + mensagem atual + instrucoes do sistema).
5. Chama o LLM (Orquestrador) com a lista de tools disponíveis.
6. Se o LLM retornar tool calls, executa cada tool e devolve os resultados ao LLM.
7. Repete ate o LLM retornar uma resposta final (sem tool calls pendentes).
8. Envia a resposta via bot-send.
9. Persiste o novo turno na memoria (Supabase + invalida cache Redis da sessao).
10. Atualiza o CRM com o ultimo contato e stage se necessario.

Arquivos relevantes: `app/worker.py`, `app/agent.py`.

### 4. Memory (Chat Memory)

Armazena e recupera o historico de conversas com duas camadas:

- **Redis (cache quente):** sessao dos ultimos N turnos, TTL de 2 horas. Evita round-trip ao Supabase em mensagens consecutivas rapidas.
- **Supabase Postgres (persistencia):** tabela compativel com o schema `n8n_chat_*` existente. Toda vez que um turno e concluido, o par (user_message, assistant_response) e gravado no Supabase e o cache Redis e atualizado.

Formato de cada mensagem armazenada:

```json
{
  "session_id": "phone_number",
  "role": "user | assistant",
  "content": "texto da mensagem",
  "timestamp": "2026-04-16T10:00:00Z",
  "metadata": {}
}
```

Arquivos relevantes: `app/memory.py`.

### 5. Tools

Functions chamadas pelo LLM via tool calling nativo. Cada tool e uma funcao Python async com schema JSON declarado.

| Tool | Descricao | Integracao |
|------|-----------|------------|
| `rag_tool` | Busca semantica nos knowledge files | Supabase pgvector, tabela `documents` |
| `calendar_tool` | Listar slots, criar, cancelar eventos | Google Calendar API (service account) |
| `crm_tool` | Ler e atualizar dados do lead | Supabase, tabela `contacts` |
| `notify_tool` | Enviar notificacao de agendamento ao Gastao | WhatsApp via bot-send |

Cada tool recebe parametros tipados, executa a operacao e retorna um dicionario com `success`, `data` e opcionalmente `error`. O worker passa o retorno de volta ao LLM como `tool_result`.

Arquivos relevantes: `app/tools/rag.py`, `app/tools/calendar.py`, `app/tools/crm.py`, `app/tools/notify.py`.

### 6. Audio Pipeline

Ativado apenas quando o tipo de mensagem e `audio`.

1. Faz download do arquivo de midia via URL temporaria da Meta Graph API (autenticado com `META_ACCESS_TOKEN`).
2. Envia o arquivo para a API de transcricao do Gemini (independente do LLM principal configurado).
3. Normaliza o texto transcrito: remove hesitacoes, padroniza pontuacao.
4. O texto normalizado entra no fluxo normal como se fosse uma mensagem de texto.

Gemini e usado fixo para transcricao porque oferece qualidade superior em portugues brasileiro e suporte nativo a audio WhatsApp (ogg/opus).

Arquivos relevantes: `app/audio.py`.

### 7. Output (bot-send)

Envio da resposta final ao lead via o endpoint Next.js ja em producao.

```
POST https://agente.casaldotrafego.com/api/whatsapp/bot-send
Content-Type: application/json

{
  "phone_number_id": "115216611574100",
  "to": "{phone_number}",
  "message": "{resposta do agente}"
}
```

O bot-send ja lida com formatacao, retry e entrega via Meta Graph API. Nao e responsabilidade deste servico.

Arquivos relevantes: `app/output.py`.

### 8. Cron (APScheduler)

Follow-up automatico integrado ao mesmo processo FastAPI.

- Scheduler: `APScheduler` com `AsyncIOScheduler`.
- Intervalo: a cada 30 minutos (configuravel via `FOLLOWUP_INTERVAL_MINUTES`).
- Logica: consulta `contacts` no Supabase buscando leads com `follow_up_at <= now()` e `stage NOT IN ('agendado', 'realizada', 'sem_interesse', 'perdido', 'bloqueado')`.
- Para cada lead elegivel: gera mensagem de follow-up contextualizada e envia via bot-send.
- Atualiza `follow_up_at` para evitar reenvio no proximo ciclo.

Arquivos relevantes: `app/followup.py`.

---

## Fluxo de uma mensagem de texto

```
1. Meta envia POST /webhook com payload JSON
2. FastAPI valida HMAC-SHA256
3. Extrai: phone_number, message_text, message_id
4. RPUSH queue:{phone_number} payload -> retorna 200 OK para Meta
5. Worker consumer faz BLPOP na fila
6. Carrega historico: GET Redis key session:{phone_number}
   -> cache miss? Busca Supabase, popula Redis
7. Monta messages array: [system_prompt] + [historico] + [user_message]
8. Chama LLM com tools declaradas
9. LLM retorna tool_call: rag_tool(query="...")
10. Worker executa rag_tool -> retorna chunks relevantes
11. Worker devolve tool_result ao LLM
12. LLM retorna resposta final em texto
13. POST bot-send com resposta
14. Persiste turno no Supabase
15. Atualiza Redis session:{phone_number} com novo turno
16. Atualiza contacts: last_message_at, stage se mudou
```

---

## Fluxo de uma mensagem de audio

```
1. Meta envia POST /webhook com tipo audio e media_id
2. FastAPI valida HMAC e identifica tipo = audio
3. RPUSH queue:{phone_number} {type: "audio", media_id: "..."} -> 200 OK
4. Worker consumer faz BLPOP
5. Identifica tipo audio -> chama Audio Pipeline:
   a. GET https://graph.facebook.com/v19.0/{media_id}?access_token=...
      -> retorna URL temporaria do arquivo
   b. Download do arquivo ogg/opus
   c. POST Gemini Transcription API com o arquivo
   d. Recebe texto transcrito
   e. Normaliza texto
6. Texto normalizado substitui o payload original
7. Fluxo continua identico ao fluxo de texto (passos 6-16 acima)
```

---

## Fluxo do follow-up

```
1. APScheduler dispara a cada 30 minutos
2. Follow-up Worker executa:
   a. SELECT * FROM contacts
      WHERE follow_up_at <= NOW()
        AND stage NOT IN ('agendado','realizada','sem_interesse','perdido','bloqueado')
      LIMIT 50
   b. Para cada lead:
      i.  Carrega ultimas N mensagens do historico (Supabase)
      ii. Chama LLM com prompt de follow-up + historico
      iii. LLM gera mensagem contextualizada
      iv.  POST bot-send com mensagem
      v.   UPDATE contacts SET follow_up_at = NOW() + INTERVAL '4 hours',
                               last_followup_at = NOW()
           WHERE phone = lead.phone
3. Logs de sucesso/falha por lead
```

---

## Integracoes externas

### Meta (WhatsApp Business API)

- **Webhook:** Meta envia `POST /webhook` para a URL publica do servico.
- **Verificacao:** `GET /webhook` responde ao challenge na configuracao inicial.
- **Autenticacao:** `X-Hub-Signature-256` no header, validado com `WEBHOOK_SECRET`.
- **Download de midia:** `GET https://graph.facebook.com/v19.0/{media_id}` com `Bearer META_ACCESS_TOKEN`.
- **Envio:** delegado ao bot-send do frontend Next.js.
- `phone_number_id`: `115216611574100`.

### Supabase (`cfjyxdqrathzremxdkoi`, us-west-2)

| Tabela | Uso |
|--------|-----|
| `documents` | RAG: busca por similaridade com `pgvector` |
| `contacts` | CRM: leitura e escrita do perfil e stage do lead |
| `n8n_chat_messages` | Memory: historico de conversas (schema compativel) |

Acesso via `supabase-py` com `SUPABASE_URL` e `SUPABASE_SERVICE_KEY`.

### Google Calendar

- Autenticacao via service account JSON (`GOOGLE_SERVICE_ACCOUNT_JSON`).
- Operacoes: listar slots livres, criar evento, cancelar evento.
- Calendar ID configuravel via `GOOGLE_CALENDAR_ID`.
- SDK: `google-api-python-client` + `google-auth`.

### bot-send (Next.js Frontend)

- Endpoint: `POST https://agente.casaldotrafego.com/api/whatsapp/bot-send`
- Autenticacao: header `Authorization: Bearer BOT_SEND_SECRET`
- Payload: `{ phone_number_id, to, message }`
- Cliente HTTP: `httpx.AsyncClient` com timeout de 15s e 2 retries.
- O frontend nao e alterado.

---

## Decisoes de arquitetura

### Redis queue por phone_number

**Problema:** sem fila, duas mensagens chegando simultaneamente do mesmo lead criam duas chamadas paralelas ao LLM. Ambas carregam o mesmo historico, geram respostas sem contexto uma da outra e causam escrita concorrente na memoria.

**Solucao:** cada `phone_number` tem sua propria lista Redis. O handler do webhook apenas publica (`RPUSH`) e retorna `200` em microsegundos. Um consumer por fila processa as mensagens em ordem, com o historico sempre atualizado antes da proxima.

**Alternativa descartada:** locks distribuidos (Redis SET NX). Mais complexo, sujeito a deadlocks e nao garante ordem.

### Tool calling nativo do LLM

**Problema:** no n8n, as tools sao sub-workflows encadeados. Adicionar uma nova tool exige criar um novo workflow, reconectar nodes e lidar com o formato de troca de dados do n8n.

**Solucao:** tools sao funcoes Python com schema JSON declarado no formato padrao de function calling (OpenAI-compatible, suportado por Claude e Gemini). O LLM decide quais tools chamar. O worker executa. Adicionar uma nova tool e adicionar um arquivo `.py` e registrar no manifesto.

### LLM configuravel via env

**Problema:** n8n tem o provider Gemini hard-coded nos nodes. Trocar exige reconfigurar manualmente.

**Solucao:** o provider e o modelo sao definidos por variaveis de ambiente (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`). O worker usa uma interface abstrata (`LLMClient`) com implementacoes para Anthropic, Google e qualquer provider OpenAI-compatible. Trocar de Claude para Gemini e uma alteracao de `.env` sem mudanca de codigo.

**Excecao:** `rag_tool` usa o modelo de embedding do Supabase (fixo). `audio pipeline` usa Gemini fixo para transcricao (qualidade em pt-BR).

### bot-send mantido intacto

**Problema:** reescrever o envio de mensagens exigiria replicar a logica de formatacao, rate limiting e retry ja existente no Next.js, alem de afetar um componente em producao.

**Solucao:** o novo servico Python trata o bot-send como uma API externa estavel. Um simples `POST httpx` substitui qualquer integracao direta com a Meta Graph API. Se o frontend precisar mudar no futuro, e uma alteracao isolada.

### APScheduler no mesmo processo

**Problema:** o cron de follow-up no n8n e um workflow separado. No Python, poderia ser um servico separado (Celery Beat, por exemplo).

**Solucao:** para o escopo de MVP, o `APScheduler` rodando dentro do mesmo processo FastAPI e suficiente. Evita infra adicional, compartilha as mesmas conexoes de banco e e facil de monitorar. Se a carga crescer, o scheduler pode ser extraido para um worker separado sem mudancas na logica de negocio.

### Deploy Docker + Railway

**Problema:** n8n requer sua propria infra ou cloud gerenciada. O novo servico precisa de deploy simples, logs acessíveis e escalabilidade basica.

**Solucao:** `Dockerfile` com imagem Python 3.12 slim. `docker-compose.yml` para desenvolvimento local com Redis incluso. Railway para producao: conecta ao repositorio, le o Dockerfile, expoe a porta e gerencia variaveis de ambiente via painel. Redis provisionado como servico adicional no Railway ou via `REDIS_URL` apontando para instancia externa.
