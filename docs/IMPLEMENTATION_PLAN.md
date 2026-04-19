# Plano de Implementacao — mvp_agent_vibe

Agente SDR WhatsApp em Python puro. Substitui workflow n8n (JmiydfZHpeU8tnic) em producao.

**Stack:** Python 3.12, FastAPI, Redis, Supabase, APScheduler, httpx, google-api-python-client

---

## Fase 1: Webhook Handler

**Objetivo:** Criar o ponto de entrada HTTP do sistema, capaz de responder a verificacao da Meta e receber mensagens reais do WhatsApp, normalizando o payload.

**Entregavel concreto:** Servidor FastAPI rodando localmente com rotas `GET /webhook` e `POST /webhook`. Ao receber uma mensagem de texto, loga no console o phone e o texto normalizados. Ao receber um audio, loga o audio_id.

**Criterio de teste:**
1. Simular verificacao Meta: `GET /webhook?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=12345` deve retornar `12345`.
2. Enviar payload POST simulado com mensagem de texto e verificar log com phone e texto corretos.
3. Enviar payload POST simulado com audio e verificar log com audio_id.
4. Enviar payload POST com evento `statuses` (delivery receipt) e verificar que nao gera log de mensagem.

**Dependencias de fase anterior:** Nenhuma. E a fase inicial.

**Riscos e atencoes:**
- A Meta exige resposta HTTP 200 em menos de 5 segundos. Qualquer processamento deve ser assincrono (enfileirar e retornar 200 imediatamente).
- Validar `X-Hub-Signature-256` desde o inicio para nao aceitar payloads forjados em producao.
- Testar com payload real da Meta antes de avancar para Fase 2 (usar ngrok para expor localhost temporariamente).

---

## Fase 2: Redis Queue e Worker Skeleton

**Objetivo:** Implementar a fila por numero de telefone com session lock, garantindo que mensagens do mesmo contato sejam processadas sequencialmente. Criar o worker assincrono que consome a fila.

**Entregavel concreto:** Mensagens recebidas pelo webhook sao enfileiradas no Redis. Worker assincrono processa uma mensagem por vez por phone, loga o conteudo e retorna. Session lock impede concorrencia por sessao. Retry com dead-letter apos 3 falhas.

**Criterio de teste:**
1. Enviar 3 mensagens rapidas do mesmo phone e verificar nos logs que sao processadas sequencialmente (nao em paralelo).
2. Enviar mensagens de dois phones diferentes e verificar que sao processadas em paralelo.
3. Simular falha no worker para o primeiro phone e verificar que o segundo nao e afetado.
4. Apos 3 falhas simuladas, verificar que a mensagem aparece em `queue:dead:{phone}` no Redis.

**Dependencias de fase anterior:** Fase 1 (webhook enfileira mensagens).

**Riscos e atencoes:**
- TTL do lock deve ser maior que o tempo maximo de resposta do LLM (usar 90 segundos como padrao inicial).
- Testar o cenario de lock orfao: simular crash do worker com lock ativo e verificar que o lock expira e a proxima mensagem e processada.
- Redis deve estar rodando localmente para desenvolvimento. Usar `docker run -p 6379:6379 redis:alpine` se nao tiver Redis instalado.

---

## Fase 3: Chat Memory Unificada

**Objetivo:** Implementar persistencia e recuperacao do historico de conversa, com Supabase como armazenamento duravel e Redis como cache de sessoes ativas.

**Entregavel concreto:** Funcoes `append_message` e `get_history` funcionando. Historico persistido na tabela `chat_sessions` do Supabase. Cache Redis com TTL 30 minutos. `get_history` retorna as ultimas 50 mensagens em ordem cronologica.

**Criterio de teste:**
1. Appender 5 mensagens alternando roles (user/assistant) e verificar que `get_history` retorna todas na ordem correta.
2. Verificar no painel Supabase que as mensagens foram persistidas na tabela `chat_sessions`.
3. Verificar no Redis que o cache existe com TTL proximo de 1800 segundos.
4. Simular expirar o cache (deletar chave Redis) e verificar que `get_history` recarrega do Supabase corretamente.
5. Inserir mais de 50 mensagens e verificar que `get_history` retorna exatamente 50.

**Dependencias de fase anterior:** Nenhuma dependencia direta de Fase 1-2, mas sera integrada ao worker na Fase 4.

**Riscos e atencoes:**
- Criar a tabela `chat_sessions` manualmente no Supabase antes de testar. Nao confundir com as tabelas `n8n_chat_*` do sistema legado.
- Adicionar index em `(phone, timestamp DESC)` para performance da query de historico.
- Testar com conexao Supabase real (nao mockar) para validar o schema e as queries.

---

## Fase 4: Agent Core

**Objetivo:** Implementar o nucleo do agente com suporte a multiplos LLM providers, carregamento do system prompt via YAML e loop de tool calling. Integrar com memory/ para historico de conversa.

**Entregavel concreto:** Worker chama o agente com phone e mensagem, o agente carrega o historico, envia ao LLM com system prompt correto, executa o loop de tool calling (com ferramentas mockadas retornando dados fixos) e retorna uma resposta de texto. Fallback de output vazio funciona. Resposta e logada no console.

**Criterio de teste:**
1. Configurar `LLM_PROVIDER=anthropic` (ou gemini/openai) e enviar uma mensagem. Verificar resposta coerente do LLM.
2. Forcar retorno vazio do LLM (mock) e verificar que o fallback dispara e retorna mensagem padrao.
3. Forcar retorno de `tool_use` do LLM (mock) e verificar que o loop executa a ferramenta mockada e reenvio ao LLM.
4. Verificar que o historico da conversa e enviado corretamente ao LLM nas mensagens subsequentes.
5. Trocar `LLM_PROVIDER` para outro provider e verificar que o agente funciona sem alteracoes no codigo principal.

**Dependencias de fase anterior:** Fase 2 (worker), Fase 3 (memory).

**Riscos e atencoes:**
- Diferenca de formato entre providers para tool calling e significativa. Validar o adaptador para cada provider antes de prosseguir.
- Limite de iteracoes do loop (max 5) e essencial para evitar custo excessivo em caso de bug nas ferramentas.
- Manter o system prompt em YAML externo desde o inicio: facilita ajustes sem redeploy.
- Testar com o system prompt real do CLOSER/Hormozi para validar comportamento do agente.

---

## Fase 5: RAG Tool

**Objetivo:** Implementar busca semantica na base de conhecimento do Supabase via pgvector, gerando embeddings com o provider LLM configurado e retornando chunks relevantes para o agente.

**Entregavel concreto:** Ferramenta `search_knowledge(query)` integrada ao agente. Quando o agente chama essa ferramenta, os chunks relevantes sao retornados e injetados no contexto. Cache de embeddings no Redis funcionando. Testar com perguntas reais sobre os servicos.

**Criterio de teste:**
1. Chamar `search_knowledge("como funciona o servico de trafego pago")` e verificar que retorna chunks relevantes da base de conhecimento.
2. Chamar duas vezes com a mesma query e verificar que o segundo hit vem do cache Redis (logar cache hit/miss).
3. Verificar via log do agente que os chunks retornados aparecem no contexto enviado ao LLM.
4. Testar com query sem match (pergunta fora do dominio) e verificar que retorna lista vazia sem errar.

**Dependencias de fase anterior:** Fase 4 (agent core com tool calling funcionando).

**Riscos e atencoes:**
- A funcao RPC `match_documents` pode nao existir ou ter assinatura diferente no Supabase legado. Verificar antes de implementar e adaptar se necessario.
- A dimensao do embedding deve coincidir com a dimensao da coluna `embedding` na tabela `documents`. Verificar no Supabase (comum: 1536 para OpenAI, 768 para Gemini text-embedding-004).
- Se LLM_PROVIDER for `anthropic`, o Anthropic SDK nao tem API de embedding propria. Usar Voyage AI ou fallback para OpenAI embeddings independentemente do provider principal.

---

## Fase 6: CRM Tool

**Objetivo:** Implementar leitura e escrita na tabela `contacts` do Supabase, expondo funcoes de CRM como ferramentas para o agente. Garantir operacoes atomicas e consistencia de dados.

**Entregavel concreto:** Ferramentas `get_contact`, `update_stage`, `save_observation`, `increment_followup` e `upsert_last_bot_msg` integradas ao agente e funcionando contra o Supabase real. O agente consegue ler o nome do lead e atualizar o stage durante a conversa.

**Criterio de teste:**
1. Inserir um contato de teste no Supabase e verificar que `get_contact(phone)` retorna os dados corretos.
2. Chamar `update_stage(phone, "qualificado")` e verificar no Supabase que o campo foi atualizado.
3. Chamar `save_observation` duas vezes e verificar que o segundo append nao sobrescreve o primeiro.
4. Chamar `increment_followup` em paralelo (2 chamadas simultaneas) e verificar que `followup_count` incrementa 2 (nao 1, como ocorreria com read-modify-write).
5. Testar `get_contact` com phone inexistente e verificar retorno `None` sem excecao.

**Dependencias de fase anterior:** Fase 4 (agent core).

**Riscos e atencoes:**
- Verificar schema real da tabela `contacts` no Supabase antes de implementar. Pode haver campos adicionais ou nomes diferentes dos esperados.
- O incremento atomico de `followup_count` e critico: usar SQL direto via `supabase.rpc()` ou `supabase.postgrest` com UPDATE atomico, nao via read-modify-write.
- Stages validos devem ser documentados e validados no codigo para manter consistencia com o sistema legado.

---

## Fase 7: Google Calendar Tool e Notify Tool

**Objetivo:** Implementar criacao de eventos no Google Calendar, busca de slots disponiveis e notificacao automatica para Gastao via Meta Graph API apos agendamento confirmado.

**Entregavel concreto:** Ferramentas `list_slots` e `create_event` integradas ao agente. Apos `create_event`, notificacao e enviada automaticamente para +5491151133210 com os dados do evento. O agente consegue conduzir o fluxo completo de agendamento na conversa.

**Criterio de teste:**
1. Chamar `list_slots(date="amanha", duration_minutes=60)` e verificar que retorna horarios livres reais do calendario.
2. Criar um evento de teste via `create_event` e verificar que aparece no Google Calendar.
3. Verificar que a notificacao foi recebida no WhatsApp de Gastao (+5491151133210) com os dados corretos.
4. Tentar criar evento em horario ja ocupado e verificar comportamento (erro claro ou slot sugerido alternativo).
5. Simular falha na notificacao e verificar que o evento ja criado nao e revertido (notificacao e best-effort).

**Dependencias de fase anterior:** Fase 4 (agent core), Fase 6 (CRM para atualizar stage para "agendado" apos criar evento).

**Riscos e atencoes:**
- Autenticacao via service account exige que o calendario alvo seja compartilhado com o email da service account. Configurar antes dos testes.
- A notificacao usa `phone_number_id` 115216611574100 como remetente. Confirmar que este numero tem permissao para enviar mensagens para +5491151133210 na WABA.
- Disparar a notificacao como `asyncio.create_task` para nao bloquear a resposta ao lead. Tratar excecoes dentro da task.

---

## Fase 8: Audio Pipeline

**Objetivo:** Habilitar transcricao de mensagens de audio enviadas pelo lead via WhatsApp, integrando download via Meta API e transcricao via Gemini Flash.

**Entregavel concreto:** Mensagens de audio recebidas no webhook sao baixadas, transcritas e processadas pelo agente como texto. O lead pode enviar audios e receber respostas coerentes ao conteudo falado.

**Criterio de teste:**
1. Enviar audio de teste via WhatsApp real e verificar que o agente recebe o texto transcrito.
2. Verificar no log que o audio_id foi baixado e descartado da memoria apos transcricao.
3. Enviar audio com ruido ou fala rapida e verificar qualidade minima da transcricao.
4. Simular falha no download (URL expirada) e verificar que o agente responde com mensagem padrao em vez de travar.
5. Verificar que audios em portugues brasileiro sao transcritos corretamente.

**Dependencias de fase anterior:** Fase 1 (webhook normaliza audio_id), Fase 4 (agent processa o texto transcrito).

**Riscos e atencoes:**
- A URL temporaria do blob de audio expira rapidamente (aproximadamente 5 minutos). O download deve ocorrer imediatamente ao receber o audio_id, antes de qualquer processamento.
- Gemini Flash e usado especificamente para transcricao mesmo se o LLM_PROVIDER principal for outro. Garantir que `GEMINI_API_KEY` esta sempre configurado.
- Audios muito longos (mais de 2 minutos) podem gerar transcricoes extensas. Implementar truncagem com aviso se o texto transcrito ultrapassar 2000 caracteres.

---

## Fase 9: Follow-up Cron

**Objetivo:** Implementar o job agendado de follow-up que roda a cada 30 minutos, identifica leads elegiveis e envia mensagens automaticas, replicando o comportamento do workflow n8n (aBMaCWPodLaS8I6L).

**Entregavel concreto:** APScheduler rodando junto com o FastAPI (via lifespan). A cada 30 minutos, o cron consulta o Supabase, identifica leads elegiveis e envia mensagens via bot-send com o template correto para o `followup_count` de cada lead. Contadores atualizados apos envio.

**Criterio de teste:**
1. Inserir lead de teste com criterios de elegibilidade atendidos e aguardar o proximo ciclo do cron (ou disparar manualmente). Verificar mensagem recebida no WhatsApp.
2. Verificar que `followup_count` foi incrementado e `last_bot_msg_at` atualizado no Supabase apos o envio.
3. Verificar que lead com `followup_count = 7` nao e incluido na query.
4. Verificar que lead com `stage = "agendado"` nao recebe follow-up.
5. Simular lead que respondeu ha 20 minutos (dentro de 30 min) e verificar que nao recebe follow-up.

**Dependencias de fase anterior:** Fase 6 (CRM tool para queries e atualizacoes), Fase da implementacao do `output/` (bot-send).

**Riscos e atencoes:**
- O cron do n8n ja esta em producao. Nao ativar o cron Python enquanto o n8n estiver ativo para evitar envios duplicados.
- Testar templates com variavel `{nome}` usando leads com e sem nome preenchido no CRM. Implementar fallback para leads sem nome ("ola, tudo bem?").
- Batch de 10 leads com delay de 2 segundos entre envios para nao exceder rate limit da Meta (80 mensagens por segundo na WABA).

---

## Fase 10: Testes Locais e Virada de Producao

**Objetivo:** Validar o sistema completo em ambiente de staging antes de trocar a URL do webhook na Meta, desativando o n8n em producao.

**Entregavel concreto:** Sistema completo rodando em producao no servidor, webhook URL da Meta apontando para o novo sistema Python. N8n workflows de entrada (JmiydfZHpeU8tnic) desativados. Sistema monitorado por 24 horas apos virada.

**Criterio de teste:**
1. Fluxo completo end-to-end: mensagem de texto WhatsApp real, agente responde com contexto correto, CRM atualizado.
2. Fluxo de audio: audio WhatsApp real, transcricao correta, resposta coerente.
3. Fluxo de agendamento: agente cria evento no Google Calendar, notificacao recebida por Gastao.
4. Follow-up: desativar cron n8n, aguardar 30 minutos, verificar follow-up enviado pelo sistema Python.
5. Teste de carga: 5 conversas simultaneas com phones diferentes, sem degradacao ou erros.

**Dependencias de fase anterior:** Todas as fases anteriores concluidas e testadas individualmente.

**Riscos e atencoes:**
- Manter o n8n em modo desativado (nao deletar) por pelo menos 7 dias apos a virada para rollback rapido se necessario.
- Configurar monitoramento de erros (Sentry ou logs estruturados) antes da virada.
- Testar a troca de URL do webhook em horario de baixo movimento (madrugada ou fim de semana).
- Ter plano de rollback documentado: passos para reativar o n8n e reverter a URL do webhook em menos de 5 minutos.

---

## Migracao do n8n

### Checklist de Virada

**Pre-requisitos (verificar antes de iniciar a troca):**

- [ ] Sistema Python rodando em producao ha pelo menos 2 horas sem erros criticos nos logs
- [ ] Tabela `chat_sessions` criada e populada com conversas de teste
- [ ] Variaveis de ambiente todas configuradas e validadas pelo modulo `config/`
- [ ] Conexao Supabase testada (leitura e escrita na tabela `contacts`)
- [ ] Conexao Redis testada (fila e cache funcionando)
- [ ] Google Calendar autenticado e criando eventos de teste
- [ ] Notificacao para Gastao (+5491151133210) testada e recebida
- [ ] bot-send (`agente.casaldotrafego.com/api/whatsapp/bot-send`) respondendo 200
- [ ] Cron de follow-up Python testado em staging (nao ativo em producao ainda)
- [ ] N8n workflow de follow-up (aBMaCWPodLaS8I6L) identificado para desativacao
- [ ] N8n workflow principal (JmiydfZHpeU8tnic) identificado para desativacao
- [ ] N8n sub-workflow de Calendar (6EJoeyC63gDEffu2) identificado para desativacao
- [ ] Plano de rollback documentado e acessivel
- [ ] Horario de virada definido (preferencialmente fora do horario comercial)

**Sequencia de virada:**

- [ ] Pausar o workflow de follow-up n8n (aBMaCWPodLaS8I6L) primeiro
- [ ] Ativar o cron de follow-up Python
- [ ] Aguardar 30 minutos e verificar que o primeiro ciclo do cron Python executou sem erros
- [ ] Trocar URL do webhook na Meta Developer Console para o novo endpoint Python
- [ ] Pausar o workflow principal n8n (JmiydfZHpeU8tnic) imediatamente apos a troca de URL
- [ ] Enviar mensagem de teste pelo WhatsApp real e verificar resposta do sistema Python
- [ ] Monitorar logs por 30 minutos antes de considerar a virada concluida

**Validacao pos-virada:**

- [ ] Nenhuma mensagem do WhatsApp respondida pelo n8n nas ultimas 2 horas
- [ ] Supabase `contacts` sendo atualizado pelo sistema Python (verificar `last_bot_msg_at`)
- [ ] Supabase `chat_sessions` recebendo novas mensagens
- [ ] Follow-up enviado corretamente no proximo ciclo de 30 minutos
- [ ] Zero erros 5xx nos logs do servidor Python nas primeiras 24 horas

**Rollback (se necessario):**

- [ ] Reativar workflow principal n8n (JmiydfZHpeU8tnic)
- [ ] Trocar URL do webhook de volta para o endpoint n8n
- [ ] Pausar cron de follow-up Python
- [ ] Reativar workflow de follow-up n8n (aBMaCWPodLaS8I6L)
- [ ] Investigar causa raiz antes de nova tentativa de virada

**O que NAO deletar ate estabilizar (minimo 7 dias):**

- Workflows n8n (apenas manter pausados)
- Tabelas legadas `n8n_chat_*` no Supabase
- Credenciais do n8n no Meta Developer Console
