# ENV.md — mvp_agent_vibe

Referencia completa de variaveis de ambiente do agente SDR WhatsApp.

---

## Grupos de variaveis

### Meta Cloud API

Responsaveis pela recepcao de mensagens via webhook e envio via bot-send.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `META_ACCESS_TOKEN` | Token de acesso permanente da API do WhatsApp Business Cloud | Sim | `EAAxxxxxxxx...` | Meta for Developers > App > WhatsApp > API Setup > Permanent Token |
| `META_PHONE_NUMBER_ID` | ID do numero de telefone vinculado ao WhatsApp Business | Sim | `115216611574100` | Meta for Developers > App > WhatsApp > API Setup > Phone Number ID |
| `META_VERIFY_TOKEN` | Token arbitrario para verificacao do webhook pelo Meta | Sim | `meu_token_secreto_123` | Definido por voce ao configurar o webhook no painel Meta |

**Nota:** `META_PHONE_NUMBER_ID` ja tem valor fixo `115216611574100` no sistema atual. Manter o mesmo valor no novo agente.

---

### Supabase

Acesso ao banco PostgreSQL com pgvector para persistencia de leads, historico e RAG.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `SUPABASE_URL` | URL do projeto Supabase | Sim (RAG) | `https://cfjyxdqrathzremxdkoi.supabase.co` | Supabase Dashboard > Project Settings > API > Project URL |
| `SUPABASE_SERVICE_KEY` | Service role key (acesso total, sem RLS) | Sim (RAG) | `eyJhbGci...` | Supabase Dashboard > Project Settings > API > service_role key |
| `DATABASE_URL` | Connection string PostgreSQL direta via pooler (porta 6543) | **Obrigatoria** | `postgresql://postgres.cfjyxdqrathzremxdkoi:SENHA@aws-0-us-west-2.pooler.supabase.com:6543/postgres` | Supabase Dashboard > Project Settings > Database > Connection Pooling > Transaction mode |

**Nota sobre acesso ao schema `agente_vibe`:** O CRM (`tools/crm.py`) e o historico de chat (`memory/chat.py`) usam `asyncpg` com conexao direta via `DATABASE_URL`, pois o PostgREST do Supabase nao expoe schemas customizados sem configuracao adicional no dashboard. `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` sao usados apenas pelo `rag_tool` (schema `public`).

**Formato do DATABASE_URL para Supabase transaction pooler (porta 6543):** a senha deve estar URL-encoded (ex: `@` vira `%40`). Use o pooler em modo Transaction (porta 6543), nao Session (porta 5432), para compatibilidade com Railway.

---

### LLM

Configuracao do provider de linguagem. Apenas a variavel do provider ativo precisa estar definida.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `LLM_PROVIDER` | Provider ativo. Valores aceitos: `gemini`, `anthropic`, `openai` | Sim | `gemini` | Definido por voce |
| `GOOGLE_API_KEY` | API key do Google AI Studio (Gemini) | Se `LLM_PROVIDER=gemini` | `AIzaSyxxxxxx` | console.cloud.google.com > APIs > Credentials ou aistudio.google.com |
| `ANTHROPIC_API_KEY` | API key da Anthropic | Se `LLM_PROVIDER=anthropic` | `sk-ant-xxxxxxxx` | console.anthropic.com > API Keys |
| `OPENAI_API_KEY` | API key da OpenAI | Se `LLM_PROVIDER=openai` | `sk-xxxxxxxx` | platform.openai.com > API Keys |

**Boas praticas:** No MVP, comecar com `LLM_PROVIDER=gemini` (custo menor). Para trocar de provider, alterar apenas `LLM_PROVIDER` e garantir que a key correspondente esta definida.

---

### Redis

Cache de estado conversacional e fila de debounce de mensagens.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `REDIS_URL` | URL de conexao ao Redis | Sim | `redis://localhost:6379` (dev) / `redis://default:SENHA@HOST:PORT` (prod) | Redis Cloud: app.redislabs.com. Local: valor padrao |

**Nota:** Em desenvolvimento com docker-compose, o valor padrao `redis://localhost:6379` ou `redis://redis:6379` (nome do servico Docker) funciona sem configuracao adicional.

---

### Google Calendar

Integracao via service account para criacao e consulta de agendamentos.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Conteudo JSON completo da service account (alternativa ao path) | Uma das duas | `{"type":"service_account","project_id":"..."}` | Google Cloud Console > IAM > Service Accounts > Chaves > Adicionar chave JSON |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Path para o arquivo .json da service account no container | Uma das duas | `/app/secrets/service_account.json` | Path local onde o arquivo foi montado via volume Docker |
| `GOOGLE_CALENDAR_ID` | ID do calendario onde os eventos serao criados | Sim | `primary` ou `abc123@group.calendar.google.com` | Google Calendar > Configuracoes do calendario > Integracao de calendario > ID do calendario |

**Nota:** Prefira `GOOGLE_SERVICE_ACCOUNT_JSON` (conteudo inline) em producao no Railway para nao precisar montar volumes. Use `GOOGLE_SERVICE_ACCOUNT_PATH` apenas em desenvolvimento local. O email da service account precisa ter permissao de "Fazer alteracoes nos eventos" no calendario alvo.

---

### Bot-send (envio de mensagens)

Endpoint do Next.js existente que efetua o envio real via Meta Cloud API.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `BOT_SEND_URL` | URL do endpoint de envio de mensagens | Sim | `https://agente.casaldotrafego.com/api/whatsapp/bot-send` | Configuracao do Next.js existente |
| `BOT_SEND_TOKEN` | Token de autenticacao para o endpoint bot-send | Sim | `token_interno_seguro_xyz` | Definido no Next.js existente (variavel de ambiente do Vercel) |

---

### Notificacao

Numero para notificacoes internas ao operador (Gastao).

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `NOTIFY_PHONE` | Numero WhatsApp do operador para alertas internos, com DDI | Sim | `+5491151133210` | Numero pessoal do operador |

---

### Follow-up (APScheduler)

Controle dos intervalos de follow-up automatico.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `FOLLOWUP_INTERVAL_MINUTES` | Intervalo em minutos entre verificacoes do scheduler | Opcional | `30` | Padrao: `30` |
| `FOLLOWUP_FU0_DELAY_HOURS` | Horas de espera apos primeira mensagem antes de enviar FU0 | Opcional | `2` | Padrao: `2` |

---

### Aplicacao

Configuracoes gerais do servidor e ambiente.

| Variavel | Descricao | Obrigatoria | Exemplo | Onde obter |
|---|---|---|---|---|
| `APP_ENV` | Ambiente de execucao. Valores: `development`, `production` | Sim | `production` | Definido por voce |
| `LOG_LEVEL` | Nivel de log. Valores: `DEBUG`, `INFO`, `WARNING`, `ERROR` | Opcional | `INFO` | Padrao: `INFO`. Use `DEBUG` apenas em desenvolvimento |
| `PORT` | Porta onde o Uvicorn vai escutar | Opcional | `8000` | Padrao: `8000`. O Railway injeta `PORT` automaticamente |

---

## Variaveis que vem do sistema n8n atual

As variaveis abaixo ja existem no ambiente n8n e podem ser reutilizadas diretamente no novo agente. Verifique os valores atuais no painel do n8n (Settings > Environment Variables) ou no `.env` do servidor onde o n8n esta hospedado.

| Variavel | Status no n8n | Observacao |
|---|---|---|
| `META_ACCESS_TOKEN` | Existe como credencial Meta no n8n | No n8n fica em Credentials, nao como env var direta. Copiar o token de la |
| `META_PHONE_NUMBER_ID` | Hardcoded nos nodes do n8n | Valor fixo: `115216611574100` |
| `META_VERIFY_TOKEN` | Configurado no webhook do n8n | Verificar no node Webhook do n8n |
| `SUPABASE_URL` | Existe como credencial Supabase no n8n | Copiar de Credentials > Supabase |
| `SUPABASE_SERVICE_KEY` | Existe como credencial Supabase no n8n | Copiar de Credentials > Supabase |
| `GOOGLE_API_KEY` | Existe como credencial Google AI no n8n | Copiar de Credentials > Google Gemini |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Existe como credencial Google no n8n | Pode estar como arquivo ou JSON inline |
| `GOOGLE_CALENDAR_ID` | Hardcoded nos nodes do Google Calendar | Verificar nos nodes de criacao de evento |
| `BOT_SEND_URL` | Existe como variavel de ambiente no n8n | Settings > Variables |
| `BOT_SEND_TOKEN` | Existe como variavel de ambiente no n8n | Settings > Variables |
| `NOTIFY_PHONE` | Hardcoded ou como variavel no n8n | Verificar nos nodes de notificacao |

---

## Notas de seguranca

### Variaveis que NUNCA devem ser commitadas

As variaveis abaixo contem segredos de producao e nao devem aparecer em nenhum arquivo versionado (`.env`, `.env.local`, arquivos de config commitados):

- `META_ACCESS_TOKEN`
- `SUPABASE_SERVICE_KEY`
- `DATABASE_URL` (contem senha)
- `GOOGLE_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (contem chave privada RSA)
- `BOT_SEND_TOKEN`
- `REDIS_URL` (se contiver senha)

O arquivo `.env` esta listado no `.gitignore`. Nunca remova essa entrada.

### Como usar secrets no Railway

1. Acesse o painel do Railway: railway.app > seu projeto > servico do agente.
2. Va em "Variables" na sidebar do servico.
3. Adicione cada variavel individualmente pelo painel. Nao faca upload de arquivo `.env`.
4. Para `GOOGLE_SERVICE_ACCOUNT_JSON`: cole o conteudo JSON completo como valor da variavel (Railway suporta valores multiline).
5. As variaveis ficam criptografadas em repouso e sao injetadas como variavel de ambiente no container em runtime.
6. Para rotacionar um segredo: atualize o valor no painel do Railway e faca redeploy. O container anterior e descartado.

### Boas praticas adicionais

- Nunca logue valores de variaveis de ambiente. Use `LOG_LEVEL=INFO` em producao.
- O `APP_ENV=production` desativa endpoints de debug (ex: `/debug`, `/test`) e ativa logs estruturados.
- Gere `META_VERIFY_TOKEN` com pelo menos 32 caracteres aleatorios: `openssl rand -hex 32`.
- Gere `BOT_SEND_TOKEN` da mesma forma e valide no middleware do Next.js via header `Authorization: Bearer`.

---

## Template .env.example

Copie este arquivo como `.env` e preencha com os valores reais. Nunca commite o `.env` preenchido.

```dotenv
# ============================================================
# mvp_agent_vibe — .env.example
# Copie para .env e preencha os valores. Nao commite o .env.
# ============================================================

# ------------------------------------------------------------
# Meta Cloud API
# ------------------------------------------------------------
META_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
META_PHONE_NUMBER_ID=115216611574100
META_VERIFY_TOKEN=gere_com_openssl_rand_hex_32

# ------------------------------------------------------------
# Supabase
# ------------------------------------------------------------
SUPABASE_URL=https://SEU_PROJECT_ID.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxxx
# DATABASE_URL so necessario para scripts de migracao
# DATABASE_URL=postgresql://postgres.SEU_PROJECT_ID:SENHA@aws-0-sa-east-1.pooler.supabase.com:6543/postgres

# ------------------------------------------------------------
# LLM — defina LLM_PROVIDER e a key correspondente
# ------------------------------------------------------------
LLM_PROVIDER=gemini

# Se LLM_PROVIDER=gemini:
GOOGLE_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Se LLM_PROVIDER=anthropic:
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Se LLM_PROVIDER=openai:
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ------------------------------------------------------------
# Redis
# ------------------------------------------------------------
# Desenvolvimento local (docker-compose):
REDIS_URL=redis://localhost:6379
# Producao (Redis Cloud):
# REDIS_URL=redis://default:SENHA@HOST:PORT

# ------------------------------------------------------------
# Google Calendar (service account)
# ------------------------------------------------------------
# Opcao 1: conteudo JSON inline (recomendado para Railway)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"SEU_PROJETO","private_key_id":"xxx","private_key":"-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n","client_email":"agente@SEU_PROJETO.iam.gserviceaccount.com","client_id":"xxx","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}

# Opcao 2: path para arquivo (dev local com volume Docker)
# GOOGLE_SERVICE_ACCOUNT_PATH=/app/secrets/service_account.json

GOOGLE_CALENDAR_ID=primary

# ------------------------------------------------------------
# Bot-send (Next.js)
# ------------------------------------------------------------
BOT_SEND_URL=https://agente.casaldotrafego.com/api/whatsapp/bot-send
BOT_SEND_TOKEN=token_interno_gerado_com_openssl_rand_hex_32

# ------------------------------------------------------------
# Notificacao interna
# ------------------------------------------------------------
NOTIFY_PHONE=+5491151133210

# ------------------------------------------------------------
# Follow-up (APScheduler)
# ------------------------------------------------------------
FOLLOWUP_INTERVAL_MINUTES=30
FOLLOWUP_FU0_DELAY_HOURS=2

# ------------------------------------------------------------
# Aplicacao
# ------------------------------------------------------------
APP_ENV=development
LOG_LEVEL=INFO
PORT=8000
```
