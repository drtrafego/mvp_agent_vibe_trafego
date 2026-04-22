# Documentacao de Modulos — mvp_agent_vibe

Agente SDR WhatsApp em Python puro. Substitui o workflow n8n em producao (JmiydfZHpeU8tnic).

---

## 1. webhook/

**Proposito:** Ponto de entrada HTTP do sistema. Recebe eventos do WhatsApp Business API (Meta), valida a origem e normaliza o payload antes de enfileirar para processamento.

**Entradas:**
- `GET /webhook`: query params `hub.mode`, `hub.verify_token`, `hub.challenge` (verificacao inicial Meta)
- `POST /webhook`: payload JSON da Meta Graph API (mensagens de texto, audio, botoes, status de entrega)

**Saidas:**
- `GET`: retorna `hub.challenge` como texto plano em caso de sucesso, 403 em caso de token invalido
- `POST`: retorna `{"status": "ok"}` com HTTP 200 imediatamente; enfileira a mensagem no Redis para processamento assincrono

**Dependencias:**
- FastAPI (framework HTTP)
- `queue/` (enfileirar mensagens normalizadas)
- `config/` (VERIFY_TOKEN, validacao de variaveis)

**Notas de implementacao:**
- O endpoint POST deve retornar 200 imediatamente, sem aguardar processamento. A Meta reencaminha mensagens se nao receber 200 em menos de 5 segundos.
- Ignorar eventos que nao sejam `messages` (ex: `statuses` de entrega). Filtrar por `entry[0].changes[0].value.messages`.
- Normalizar o numero de telefone: remover `+` e garantir formato E.164 sem prefixo. Exemplo: `5511999999999`.
- Mensagens de audio chegam com `type: "audio"` e campo `audio.id`. Encaminhar para o modulo `audio/` antes de enfileirar o texto transcrito.
- Validar HMAC-SHA256 da assinatura `X-Hub-Signature-256` quando disponivel, para rejeitar requisicoes forjadas.

---

## 2. queue/

**Proposito:** Gerenciar a fila de mensagens por numero de telefone, garantindo processamento sequencial e sem concorrencia por sessao. Evita que duas mensagens do mesmo contato sejam processadas simultaneamente.

**Entradas:**
- Mensagem normalizada do `webhook/` com campos: `phone`, `message_text`, `timestamp`, `message_type`
- Comandos de controle: enfileirar, dequeue, adquirir lock, liberar lock

**Saidas:**
- Mensagem retirada da fila entregue ao worker
- Lock Redis por `phone` com TTL configuravel (padrao 60 segundos)
- Confirmacao de enfileiramento (retorno para o webhook)

**Dependencias:**
- `redis-py` async (`aioredis` ou `redis.asyncio`)
- `agent/` (worker chama o agente para processar a mensagem)
- `config/` (REDIS_URL, LOCK_TTL)

**Notas de implementacao:**
- Usar chave Redis `queue:{phone}` como lista (LPUSH / BRPOP).
- Session lock via `SET lock:{phone} 1 EX {TTL} NX`. Se lock existe, a mensagem fica na fila e o worker tenta novamente apos TTL expirar.
- Worker loop assincrono: um consumer por instancia, processa uma mensagem por vez por phone. Para escalar, usar consumer groups do Redis Streams em versoes futuras.
- TTL do lock deve ser maior que o tempo maximo esperado de resposta do LLM (sugerido: 90 segundos).
- Implementar dead-letter: apos 3 tentativas falhas, mover mensagem para `queue:dead:{phone}` e logar erro.
- Retry com backoff exponencial: 2s, 4s, 8s entre tentativas.

---

## 3. memory/

**Proposito:** Persistir e recuperar o historico de conversa por numero de telefone. Combina armazenamento duravel no Supabase com cache rapido no Redis para conversas ativas.

**Entradas:**
- `phone` (string): identificador da sessao
- `role` (string): `"user"` ou `"assistant"`
- `content` (string): texto da mensagem
- Operacoes: `append_message`, `get_history`, `clear_cache`

**Saidas:**
- Lista de dicionarios `{role, content, timestamp}` com as ultimas 50 mensagens da sessao
- Confirmacao de escrita no Supabase e no cache Redis

**Dependencias:**
- `asyncpg` (pool de conexoes direto ao PostgreSQL, tabela `agente_vibe.chat_sessions`)
- `redis-py` async (cache de sessoes ativas, TTL 30 minutos)
- `config/` (DATABASE_URL, REDIS_URL)

**Notas de implementacao:**
- Schema da tabela `agente_vibe.chat_sessions`: `id (uuid)`, `phone (text)`, `role (text)`, `content (text)`, `created_at (timestamptz)`. Index em `(phone, created_at)`.
- Estrategia de cache: ao buscar historico, verificar Redis primeiro (`history:{phone}`). Se miss, buscar PostgreSQL via asyncpg, popular cache com TTL de 30min e retornar.
- Ao escrever, inserir par (user, assistant) no PostgreSQL via `executemany`, depois reconstruir e salvar cache Redis.
- Limitar historico retornado ao agente em 50 mensagens (`ORDER BY created_at DESC LIMIT 50`, depois reverter ordem).
- Acesso direto via asyncpg necessario porque o PostgREST do Supabase nao expoe o schema `agente_vibe` sem configuracao no dashboard.

---

## 4. agent/

**Proposito:** Nucleo do agente SDR. Orquestra o loop de raciocinio com o LLM, gerencia chamadas de ferramentas (tool calling) e retorna a resposta final para envio ao contato.

**Entradas:**
- `phone` (string): identificador da sessao
- `message` (string): mensagem atual do usuario (texto ja transcrito, se audio)
- Historico de conversa (buscado internamente via `memory/`)

**Saidas:**
- `response_text` (string): resposta do agente para ser enviada ao usuario via `output/`
- Efeitos colaterais: chamadas de ferramentas (RAG, CRM, Calendar, Notify)

**Dependencias:**
- `memory/` (historico da sessao)
- `tools/rag.py`, `tools/crm.py`, `tools/calendar.py`, `tools/notify.py`
- `config/` (LLM_PROVIDER, system prompt YAML)
- SDK do LLM configurado: `anthropic`, `google-generativeai` ou `openai`

**Notas de implementacao:**
- LLM_PROVIDER aceita valores: `"anthropic"`, `"gemini"`, `"openai"`. Instanciar o cliente correto em tempo de inicializacao. Manter interface unica interna (`llm_call(messages, tools)`) com adaptadores por provider.
- System prompt carregado do arquivo YAML via `config/`. Nao hardcodar o prompt no codigo.
- Tool calling loop: enviar mensagens ao LLM, se retornar `tool_use`, executar a ferramenta correspondente, adicionar resultado ao historico de mensagens, reenviar ao LLM. Repetir ate obter resposta de texto ou atingir limite de iteracoes (max 5 iteracoes para evitar loop infinito).
- Fallback de output vazio: se o LLM retornar string vazia ou None, reenviar com instrucao explodita ("Responda em portugues com pelo menos uma frase."). Se persistir na segunda tentativa, logar e retornar mensagem de fallback padrao.
- Manter ferramentas definidas como JSON schema compativel com o provider ativo. Usar modulo de adaptacao para converter schema entre formatos (Anthropic usa `input_schema`, OpenAI usa `parameters`).

---

## 5. tools/rag.py

**Proposito:** Buscar chunks de conhecimento relevantes no Supabase via busca semantica por similaridade vetorial (pgvector), usando embedding gerado pelo proprio LLM configurado.

**Entradas:**
- `query` (string): texto da pergunta ou contexto atual da conversa
- `top_k` (int, opcional): numero de chunks a retornar (padrao 5)

**Saidas:**
- Lista de strings com os chunks de texto mais relevantes, prontos para injecao no contexto do agente

**Dependencias:**
- Supabase Python SDK (tabela `documents` com coluna `embedding vector(1536)` ou dimensao compativel)
- SDK do LLM configurado (para gerar embedding da query)
- `config/` (SUPABASE_URL, SUPABASE_KEY, LLM_PROVIDER)

**Notas de implementacao:**
- Tabela `documents` ja existe no projeto Supabase `cfjyxdqrathzremxdkoi` do sistema legado. Reutilizar sem alteracoes de schema.
- Gerar embedding da query com o mesmo provider configurado em LLM_PROVIDER. Para Anthropic, usar `voyage-3` via API separada ou fallback para OpenAI `text-embedding-3-small`. Para Gemini, usar `models/text-embedding-004`. Para OpenAI, usar `text-embedding-3-small`.
- Chamar RPC Supabase `match_documents(query_embedding, match_count)` ou usar `.rpc()` com funcao PL/pgSQL existente.
- Se a funcao RPC nao existir, fazer query manual: `SELECT content, 1 - (embedding <=> $1) AS similarity FROM documents ORDER BY similarity DESC LIMIT $2`.
- Retornar apenas o campo `content` dos chunks. Nao incluir metadados na resposta ao agente (manter contexto limpo).
- Cache de embedding por query usando Redis com TTL de 10 minutos (evitar recomputacao de queries identicas).

---

## 6. tools/crm.py

**Proposito:** Interface de leitura e escrita na tabela `contacts` do Supabase. Gerencia stage do lead, observacoes do SDR, contagem de follow-ups e timestamps de ultima interacao.

**Entradas:**
- `phone` (string): identificador do contato (chave primaria ou campo unico)
- Operacoes e seus parametros:
  - `get_contact(phone)`: sem parametros adicionais
  - `update_stage(phone, stage)`: novo stage (string)
  - `save_observation(phone, observation)`: texto livre
  - `increment_followup(phone)`: sem parametros adicionais
  - `upsert_last_bot_msg(phone)`: atualiza `last_bot_msg_at` para `now()`

**Saidas:**
- `get_contact`: dicionario com todos os campos do contato ou `None` se nao encontrado
- Demais operacoes: booleano de sucesso ou excecao em caso de falha

**Dependencias:**
- `asyncpg` (pool de conexoes direto ao PostgreSQL, tabela `agente_vibe.contacts`)
- `config/` (DATABASE_URL)

**Notas de implementacao:**
- Tabela `agente_vibe.contacts`. Campos: `phone`, `name`, `stage`, `observacoes_sdr`, `followup_count`, `nicho`, `last_lead_msg_at`, `last_bot_msg_at`, `created_at`, `updated_at`.
- `get_contact(phone)` usa `INSERT ... ON CONFLICT (phone) DO UPDATE` para upsert atomico. Index unico parcial em `phone WHERE phone IS NOT NULL`.
- `update_contact(phone, **kwargs)` monta SET dinamico com parametros posicionais (`$1`, `$2`, ...). Sempre atualiza `updated_at = now()`.
- `append_observation` concatena linha com timestamp `[HH:MM] texto` ao campo `observacoes_sdr`. Limita a 20 linhas historicas.
- Stages validos: `"novo"`, `"qualificando"`, `"interesse"`, `"agendado"`, `"realizada"`, `"sem_interesse"`, `"perdido"`, `"bloqueado"`. Validar em `advance_stage` antes de gravar.
- Acesso direto via asyncpg: nao usa supabase-py SDK (que requer schema exposure no PostgREST para schemas customizados).

---

## 7. tools/calendar.py e tools/notify.py

**Proposito (calendar.py):** Criar eventos no Google Calendar, buscar slots disponiveis e retornar o link do evento criado para confirmacao ao lead.

**Proposito (notify.py):** Enviar notificacao de novo agendamento para Gastao (+5491151133210) via Meta Graph API diretamente, com dados do evento criado.

**Entradas (calendar.py):**
- `create_event(title, start_datetime, end_datetime, attendee_email, description)`: dados do evento
- `list_slots(date, duration_minutes)`: data desejada e duracao da consulta

**Entradas (notify.py):**
- `event_data` (dict): campos do evento (titulo, data, hora, nome do lead, phone do lead, htmlLink)

**Saidas:**
- `create_event`: dicionario com `event_id`, `htmlLink`, `start`, `end`
- `list_slots`: lista de strings com horarios disponiveis no formato legivel
- `notify.py`: booleano de sucesso da requisicao POST para Meta Graph API

**Dependencias:**
- `google-api-python-client`, `google-auth` (calendar.py)
- `httpx` (notify.py)
- `config/` (GOOGLE_SERVICE_ACCOUNT_JSON ou GOOGLE_CREDENTIALS_PATH, META_ACCESS_TOKEN, META_PHONE_NUMBER_ID=115216611574100, GASTAO_PHONE=+5491151133210)

**Notas de implementacao:**
- Autenticar Google Calendar via service account JSON (mais estavel que OAuth user flow para producao). Compartilhar o calendario alvo com o email da service account.
- `list_slots` deve consultar eventos existentes no dia e retornar janelas livres, considerando horario comercial configuravel (ex: 09:00-18:00, segunda a sexta).
- Disparar `notify.py` como `asyncio.create_task` imediatamente apos `create_event` retornar com sucesso. Nao bloquear a resposta ao lead.
- `notify.py` usa endpoint `POST https://graph.facebook.com/v19.0/115216611574100/messages` com payload de mensagem de texto simples.
- Formatar mensagem de notificacao com: nome do lead, telefone, data e hora do evento, link do Google Calendar.
- Tratar erro 401 do Google Calendar (token expirado) com retry automatico de refresh via `google-auth`.

---

## 8. audio/

**Proposito:** Receber o ID de um audio enviado pelo lead via WhatsApp, baixar o blob de audio via Meta Graph API e transcrever usando Gemini Flash, retornando o texto normalizado para processamento pelo agente.

**Entradas:**
- `audio_id` (string): ID do audio recebido no payload do webhook
- `phone` (string): numero do remetente (para logging)

**Saidas:**
- `transcribed_text` (string): texto transcrito e normalizado, pronto para o pipeline do agente
- Em caso de falha: `None` ou string vazia (tratado como mensagem vazia no agente)

**Dependencias:**
- `httpx` (download do audio via Meta Graph API)
- `google-generativeai` SDK (transcricao com `gemini-1.5-flash` ou `gemini-2.0-flash`)
- `config/` (META_ACCESS_TOKEN, META_PHONE_NUMBER_ID, GEMINI_API_KEY)

**Notas de implementacao:**
- Fluxo em dois passos: (1) GET `https://graph.facebook.com/v19.0/{audio_id}` para obter URL temporaria do blob; (2) GET na URL temporaria com header `Authorization: Bearer {META_ACCESS_TOKEN}` para baixar o arquivo OGG/OPUS.
- A URL temporaria expira em aproximadamente 5 minutos. Fazer o download imediatamente apos obter a URL.
- Enviar o arquivo de audio para o Gemini Flash como parte de uma mensagem multimodal. Usar `Part.from_bytes(audio_bytes, mime_type="audio/ogg")`.
- Instrucao de transcricao para o Gemini: "Transcreva o audio a seguir em portugues brasileiro. Retorne apenas o texto transcrito, sem comentarios adicionais."
- Limpar audio temporario da memoria apos transcricao (nao persistir em disco).
- Se LLM_PROVIDER nao for `"gemini"`, usar a API Gemini especificamente para transcricao independente do provider principal (Gemini Flash e o melhor custo-beneficio para essa tarefa).

---

## 9. followup/

**Proposito:** Cron job que roda a cada 30 minutos para identificar leads elegiveis para follow-up e enviar mensagens automaticas via bot-send, replicando a logica do workflow n8n (aBMaCWPodLaS8I6L).

**Entradas:**
- Nenhuma entrada direta. Executa query no Supabase autonomamente.
- Criterios de elegibilidade (query): `stage` nao e `"agendado"` nem `"perdido"` nem `"nao_qualificado"`, `followup_count < 7`, `last_lead_msg_at` ha mais de X horas (configuravel, padrao 24h), `last_bot_msg_at` ha mais de 30 minutos.

**Saidas:**
- Mensagens enviadas via `output/` (bot-send) para cada lead elegivel
- Atualizacao de `followup_count` e `last_bot_msg_at` no CRM apos envio bem-sucedido

**Dependencias:**
- APScheduler (`AsyncIOScheduler`)
- `tools/crm.py` (buscar leads, atualizar contadores)
- `output/` (enviar mensagem via bot-send)
- `config/` (SUPABASE_URL, SUPABASE_KEY, intervalo configuravel)

**Notas de implementacao:**
- 7 templates de mensagem indexados por `followup_count` (0 a 6). Manter templates em arquivo YAML separado (`config/followup_templates.yaml`). Nao hardcodar no codigo.
- Usar `followup_count` como indice do array de templates: `templates[followup_count]`. Suportar variavel `{nome}` nos templates.
- Processar leads em batches de 10 para evitar sobrecarga. Adicionar delay de 2 segundos entre envios para respeitar rate limits da Meta.
- Iniciar o scheduler junto com o startup do FastAPI usando `lifespan` context manager.
- Logar cada envio de follow-up com phone, followup_count e timestamp.
- Nao enviar follow-up se o lead respondeu nos ultimos 30 minutos (verificar `last_lead_msg_at`).

---

## 10. config/

**Proposito:** Centralizar carregamento de variaveis de ambiente, validacao de variaveis obrigatorias na inicializacao da aplicacao e leitura do system prompt YAML.

**Entradas:**
- Arquivo `.env` na raiz do projeto
- Arquivo `config/system_prompt.yaml` com o prompt do agente (CLOSER/Hormozi framework)
- Arquivo `config/followup_templates.yaml` com os 7 templates de follow-up

**Saidas:**
- Objeto `Settings` (Pydantic BaseSettings ou dataclass) com todas as variaveis tipadas
- String do system prompt pronta para uso no agente
- Lista de templates de follow-up indexada

**Dependencias:**
- `python-dotenv`
- `pydantic-settings` (recomendado) ou `pydantic` com BaseSettings
- PyYAML

**Notas de implementacao:**
- Variaveis obrigatorias que devem falhar em startup se ausentes: `SUPABASE_URL`, `SUPABASE_KEY`, `REDIS_URL`, `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`, `LLM_PROVIDER`.
- Variaveis condicionais: `ANTHROPIC_API_KEY` obrigatorio se `LLM_PROVIDER=anthropic`; `GEMINI_API_KEY` obrigatorio se `LLM_PROVIDER=gemini`; `OPENAI_API_KEY` obrigatorio se `LLM_PROVIDER=openai`.
- Validar no startup via Pydantic validators. Falhar com mensagem clara indicando qual variavel esta faltando.
- System prompt YAML deve suportar multiplas secoes (`role`, `context`, `rules`, `tools_guidance`) que sao concatenadas em ordem.
- Expor instancia singleton `settings = Settings()` importavel por todos os modulos.

---

## 11. output/

**Proposito:** Enviar respostas do agente para o lead via endpoint bot-send do Next.js existente em producao. Gerenciar split de mensagens longas e retry automatico em caso de falha.

**Entradas:**
- `phone` (string): numero do destinatario
- `message` (string): texto completo da resposta do agente
- `max_length` (int, opcional): limite de caracteres por mensagem (padrao 1000)

**Saidas:**
- Booleano de sucesso apos envio confirmado
- Lista de strings (chunks) caso a mensagem tenha sido dividida (para logging)

**Dependencias:**
- `httpx` (cliente HTTP async)
- `config/` (BOT_SEND_URL, BOT_SEND_TOKEN se aplicavel)

**Notas de implementacao:**
- Endpoint de producao: `POST agente.casaldotrafego.com/api/whatsapp/bot-send` com body `{"phone": "...", "message": "..."}`.
- Split de mensagens: dividir em paragrafos (quebra de linha dupla). Se um paragrafo unico exceder `max_length`, dividir por sentencas. Nunca cortar palavras no meio.
- Enviar chunks com delay de 500ms entre eles para simular digitacao humana.
- Retry 3x com backoff: 1s, 2s, 4s. Logar falha apos terceira tentativa sem lancar excecao (nao derrubar o agente por falha de envio).
- Manter o Next.js intacto: nao alterar o endpoint bot-send. O output/ e apenas um cliente HTTP para ele.
- Apos envio bem-sucedido, chamar `memory/` para persistir a mensagem do assistant no historico.
