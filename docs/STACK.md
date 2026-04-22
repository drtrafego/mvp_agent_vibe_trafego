# STACK.md — mvp_agent_vibe

Documentacao tecnica da stack do agente SDR WhatsApp em Python puro.

---

## Resumo da Stack

| Componente | Tecnologia | Versao minima | Motivo |
|---|---|---|---|
| Runtime | Python | 3.12 | asyncio maduro, type hints modernos, suporte nativo a tomographia de tasks |
| Web framework | FastAPI | 0.110 | async nativo, validacao via Pydantic, docs automaticos |
| Servidor ASGI | Uvicorn[standard] | 0.29 | compativel com FastAPI, suporte a WebSocket e reload em dev |
| Fila de mensagens / cache de estado | Redis (asyncio) | 5.0 | persistencia entre restarts, pub/sub, TTL nativo |
| Banco de dados (RAG) | Supabase SDK Python | 2.0 | acesso ao schema `public` via PostgREST para pgvector/RAG |
| Banco de dados (CRM + Memory) | asyncpg | 0.29 | acesso direto ao schema `agente_vibe` via connection pool PostgreSQL |
| LLM principal | Google Gemini Flash | via google-generativeai 0.8 | custo menor no MVP, troca sem mudar codigo |
| LLM alternativo | Anthropic Claude | via anthropic 0.40 | qualidade superior para casos complexos |
| LLM fallback | OpenAI | via openai 1.0 | compatibilidade com providers alternativos |
| Agendamento | APScheduler | 3.10 | leve, no mesmo processo, suficiente para volume baixo |
| HTTP client | httpx | 0.25 | async nativo, compativel com FastAPI e httpx.AsyncClient |
| Google Calendar | google-api-python-client + google-auth | 2.0 | autenticacao via service account, sem OAuth interativo |
| Envio de mensagens | bot-send (Next.js externo) | N/A | reutiliza frontend existente sem refatoracao |
| Config | python-dotenv + pyyaml | 1.0 / 6.0 | .env para segredos, YAML para prompts e regras |
| Containerizacao | Docker + docker-compose | N/A | ambiente reproduzivel local e em CI |
| Producao | Railway | N/A | deploy simples de containers, variaveis de ambiente nativas |

---

## Detalhamento por Componente

### Python 3.12

A versao 3.12 foi escolhida por:

- `asyncio` com melhor gestao de tasks e cancelamento.
- Melhorias de performance no interpreter (~5% mais rapido que 3.11 em benchmarks reais).
- Type hints com `X | Y` (PEP 604) ja estabilizados, necessarios para o codigo tipado com mypy.
- Suporte de longo prazo: mantida com security fixes ate 2028.

### FastAPI

Framework web assincrono com:

- Validacao de payloads via Pydantic v2 (webhook do Meta, corpo das respostas LLM).
- Geracao automatica de documentacao OpenAPI (util para debug do webhook).
- Dependency injection nativo para injetar clientes Redis, Supabase e LLM.
- Tempo de startup rapido: importante para Railway onde containers sobem e caem.

### Redis (redis[asyncio])

O estado conversacional de cada lead (historico, estagio do funil, flags de follow-up) precisa sobreviver a restarts do container. Opcoes avaliadas:

- Dicionario em memoria: perderia estado em qualquer restart.
- SQLite em arquivo: sem suporte assincrono decente, problemas de locking em concorrencia.
- Redis: TTL nativo por chave, pub/sub disponivel para futuras notificacoes, cliente asyncio maduro (`redis.asyncio`).

O Redis tambem serve como debounce de mensagens (evita processar duplicatas que o Meta reenviar por timeout).

### Supabase (PostgreSQL + pgvector)

O banco `cfjyxdqrathzremxdkoi` (us-west-2) contem dois schemas:

- **`public`:** tabela `documents` com embeddings pgvector para RAG. Acessado via `supabase-py` SDK.
- **`agente_vibe`:** tabelas `contacts` (CRM) e `chat_sessions` (historico). Acessado via `asyncpg` com conexao direta.

#### Por que dois modos de acesso

O PostgREST do Supabase expoe apenas o schema `public` por padrao. Para acessar schemas customizados via SDK seria necessario configurar `pgrst.db_schemas` no dashboard Supabase, o que exige permissao de superuser que o plano free nao concede via SQL.

A solucao adotada: `asyncpg` com `DATABASE_URL` apontando para o pooler Transaction (porta 6543) acessa qualquer schema diretamente via SQL, sem restricoes do PostgREST. O SDK `supabase-py` continua sendo usado apenas para RAG (schema `public`).

### APScheduler

Responsavel pelos jobs de follow-up (FU0, FU1, FU2...). Alternativas avaliadas:

- Celery: robusto, mas exige um worker separado, broker (RabbitMQ ou Redis com configuracao adicional) e overhead operacional desproporcional para ~30 leads ativos simultaneos.
- Rq (Redis Queue): mais simples que Celery, mas ainda requer processo separado.
- APScheduler: roda no mesmo processo FastAPI via `AsyncIOScheduler`, zero infra adicional, suficiente para o volume atual.

### httpx

Usado para chamadas HTTP assincronas para:

- bot-send (envio de mensagens WhatsApp via Next.js).
- Google Calendar API (quando necessario fora do SDK).
- Eventuais callbacks de notificacao para o Gastao.

O `requests` foi descartado por ser sincrono (bloquearia o event loop do FastAPI).

### google-api-python-client + google-auth

Integracao com Google Calendar via service account:

- Sem necessidade de OAuth interativo ou refresh token manual.
- O arquivo JSON da service account e carregado via variavel de ambiente (`GOOGLE_SERVICE_ACCOUNT_JSON`).
- Permissao de escrita no calendario concedida diretamente ao email da service account nas configuracoes do Google Calendar.

### Docker + docker-compose

- Garante que o ambiente local seja identico ao de producao.
- O `docker-compose.yml` sobe FastAPI + Redis juntos, eliminando a necessidade de instalar Redis localmente.
- O `Dockerfile` usa imagem base `python:3.12-slim` para imagem final menor.

### Railway

Plataforma escolhida para producao por:

- Deploy direto via `railway up` ou push para branch configurada.
- Variaveis de ambiente gerenciadas via painel (sem `.env` em producao).
- Suporte nativo a volumes para persistencia (se necessario no futuro).
- Preco proporcional ao uso, adequado para o volume atual do MVP.

---

## LLM Flexibility

O sistema suporta tres providers de LLM atraves de uma interface comum, configurada pela variavel `LLM_PROVIDER`.

### Interface esperada

Cada provider e encapsulado em um modulo separado que expoe a mesma funcao:

```python
async def generate(prompt: str, history: list[dict]) -> str:
    ...
```

O orquestrador central chama sempre `llm.generate(...)` sem saber qual provider esta ativo.

### Providers suportados

| Provider | Variavel | SDK | Modelo padrao |
|---|---|---|---|
| Google Gemini | `LLM_PROVIDER=gemini` | `google-generativeai >= 0.8` | `gemini-2.0-flash-lite` |
| Anthropic Claude | `LLM_PROVIDER=anthropic` | `anthropic >= 0.40` | `claude-3-5-haiku-20241022` |
| OpenAI | `LLM_PROVIDER=openai` | `openai >= 1.0` | `gpt-4o-mini` |

### Como trocar de provider

1. Alterar `LLM_PROVIDER` no `.env` ou no painel do Railway.
2. Garantir que a API key correspondente esta definida (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`).
3. Reiniciar o container. Nenhuma alteracao de codigo necessaria.

### Estrategia de fallback (opcional no MVP)

Se `LLM_PROVIDER=gemini` e a chamada falhar (rate limit, timeout), o sistema pode tentar `LLM_PROVIDER=openai` como fallback. Essa logica fica no modulo `llm/router.py` e e desativada por padrao no MVP para manter simplicidade.

---

## O que foi descartado e por que

### Celery

Descartado em favor de APScheduler. O volume de ~30 leads ativos simultaneos nao justifica a complexidade operacional de um worker Celery separado mais broker configurado. APScheduler roda no mesmo processo e cobre o caso de uso com zero overhead adicional.

### SQLite

Descartado em favor de Supabase. SQLite nao tem suporte assincrono maduro, apresenta problemas de locking com multiplas coroutines e nao suporta pgvector para RAG. Alem disso, o banco Supabase ja existe com dados do n8n.

### Queue em memoria (asyncio.Queue)

Descartado em favor de Redis. Uma fila em memoria e perdida em qualquer restart do container, o que causaria perda de mensagens em processamento. Redis garante durabilidade com configuracao simples.

### OAuth para Google Calendar

Descartado em favor de service account. OAuth interativo exige que um humano autorize o acesso periodicamente e gerencie refresh tokens. A service account e permanente e gerenciada por variavel de ambiente.

### n8n como orquestrador

O sistema n8n existente apresentava tres problemas estruturais:
- Logica de LLM engessada em nodes visuais sem controle granular de prompt.
- Race conditions em flows paralelos sem mecanismo de lock confiavel.
- Impossibilidade de testar unitariamente os nos de decisao.

O agente Python substitui o n8n como orquestrador, mantendo apenas o bot-send do Next.js para nao alterar o frontend.

### Prisma / SQLAlchemy

Descartados em favor do SDK Python do Supabase. O SDK ja oferece acesso ao banco com suporte a pgvector e row-level security. Adicionar um ORM seria uma camada de indirection desnecessaria para o volume atual.

---

## Alternativas futuras

### Quando migrar APScheduler para Celery

Criterios para considerar a migracao:

- Volume de leads ativos superar 200 simultaneos.
- Necessidade de retry automatico com backoff exponencial por job.
- Necessidade de monitoramento granular de filas (Flower dashboard).
- Introducao de tasks de longa duracao (processamento de audio, batch de embeddings).

### Quando adicionar Elasticsearch

Atualmente o RAG usa pgvector com busca por similaridade de cosseno. Elasticsearch seria considerado quando:

- O volume de documentos indexados superar 100k chunks.
- Necessidade de busca hibrida (semantica + full-text com BM25).
- Latencia de busca atual superar 200ms em producao.

### Quando separar o Redis em instancia dedicada

O Redis atual pode rodar como container no docker-compose ou como instancia Redis Cloud compartilhada. Separar em instancia dedicada faz sentido quando:

- Memoria usada pelo Redis superar 80% do limite do plano atual.
- Necessidade de replicacao ou cluster para alta disponibilidade.

### Quando adicionar cache de embeddings

Os embeddings gerados para RAG podem ser cacheados no Redis com TTL longo quando:

- O custo de geracao de embeddings superar 10% do custo total de LLM.
- Os documentos indexados tiverem baixa frequencia de atualizacao.

### Quando mover para LLM proprio (self-hosted)

Consideravel apenas se:

- Volume mensal de tokens superar o threshold economico para hosting proprio (tipicamente >50M tokens/mes).
- Requisitos de privacidade de dados impedirem envio a APIs externas.
- Latencia de APIs externas se tornar gargalo medivel no SLA.
