"""
scripts/seed_rag.py

Popula a tabela `documents` no Supabase com a base de conhecimento da Claudia.
Gera embeddings via Gemini e insere via Supabase Python SDK.

Uso:
    python scripts/seed_rag.py                  # insere tudo
    python scripts/seed_rag.py --limpar         # apaga tudo e reinsere
    python scripts/seed_rag.py --categoria objecoes  # insere apenas uma categoria
"""

import argparse
import os
import sys
import time

import google.generativeai as genai
from supabase import create_client

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

EMBED_MODEL = "models/embedding-001"
TABLE = "documents"
DELAY_ENTRE_INSERTS = 0.3  # segundos, respeita rate limit do Gemini


# ---------------------------------------------------------------------------
# Base de conhecimento
# ---------------------------------------------------------------------------

DOCUMENTOS: list[dict] = [

    # -----------------------------------------------------------------------
    # PRODUTO / O QUE É O AGENTE 24 HORAS
    # -----------------------------------------------------------------------
    {
        "categoria": "produto",
        "titulo": "O que é o Agente 24 Horas",
        "content": """O Agente 24 Horas é um atendente de IA treinado especificamente para o negócio do cliente.
Ele responde no WhatsApp em tempo real, 24 horas por dia, 7 dias por semana, sem precisar de humano.
Entende áudio, texto e contexto da conversa. Lembra de tudo que o cliente já disse.
Pode agendar, qualificar leads, responder dúvidas, fazer follow-up automático e avisar o dono quando algo precisa de atenção humana.
Não é um chatbot de respostas prontas. É um agente que raciocina, usa ferramentas e toma decisões como um atendente treinado.
A diferença para um chatbot comum: o Agente 24 Horas entende contexto, não só palavras-chave. Se o cliente perguntar algo fora do script, ele responde com inteligência, não trava.""",
    },
    {
        "categoria": "produto",
        "titulo": "Como é entregue o Agente 24 Horas",
        "content": """A entrega é feita em 3 etapas:
1. Reunião de onboarding: o Gastão mapeia o negócio, os principais fluxos de atendimento, objeções mais comuns e o tom de voz da marca.
2. Configuração e treinamento: a equipe monta a base de conhecimento do agente com as informações do cliente, integra ao WhatsApp Business e ajusta o comportamento.
3. Período de calibração: nas primeiras 2 semanas, o cliente reporta ajustes e o agente é refinado até estar perfeito.

Prazo médio de entrega: 7 a 14 dias úteis após o onboarding.
O cliente não precisa saber programar. A gestão é feita pela equipe DR.TRAFEGO.""",
    },
    {
        "categoria": "produto",
        "titulo": "Integrações disponíveis",
        "content": """O Agente 24 Horas integra com:
- WhatsApp Business API (Meta oficial)
- Google Calendar (agendamento automático)
- Google Sheets (registro de leads)
- CRM via webhook (qualquer sistema com API)
- Sistemas de agendamento: Calendly, AgendaPro, Doctoralia (sob consulta)
- Instagram Direct (roadmap)

Não precisa trocar de sistema. O agente se conecta ao que o cliente já usa.""",
    },
    {
        "categoria": "produto",
        "titulo": "Segurança e LGPD",
        "content": """O Agente 24 Horas é construído sobre infraestrutura segura:
- Dados armazenados em servidores certificados (Supabase, infra AWS us-east)
- Nenhuma conversa é compartilhada com terceiros
- Conformidade com LGPD: dados do cliente são usados exclusivamente para operar o agente dele
- Possibilidade de contrato de confidencialidade (NDA) para segmentos sensíveis (saúde, jurídico, financeiro)
- O cliente pode solicitar exclusão de dados a qualquer momento

A IA não toma decisões financeiras nem envia dados bancários. Toda transação financeira é redirecionada para o humano.""",
    },

    # -----------------------------------------------------------------------
    # PREÇO E INVESTIMENTO
    # -----------------------------------------------------------------------
    {
        "categoria": "preco",
        "titulo": "Como responder sobre preço antes do valor estar construído",
        "content": """Quando o lead perguntar preço antes de entender o valor, use a virada de preço:
"Antes de falar em número, deixa eu entender melhor o seu caso para garantir que faz sentido pra você."
Depois entregue o pedaço do queijo do nicho dele.

Se insistir muito, diga:
"O investimento varia de acordo com o volume de atendimentos e as integrações necessárias. O Gastão monta uma proposta customizada na call. O que posso te dizer é que clientes com volume similar ao seu costumam recuperar o investimento nos primeiros 60 dias só com os leads que paravam de responder fora do horário."

Nunca dê número sem contexto. Preço sem valor percebido é sempre caro.""",
    },
    {
        "categoria": "preco",
        "titulo": "Posicionamento de valor do Agente 24 Horas",
        "content": """O Agente 24 Horas não compete com funcionário. Compete com o custo de não atender.
Um funcionário de atendimento custa entre R$ 2.000 e R$ 4.000 por mês com encargos, só atende em horário comercial e tira férias.
O Agente 24 Horas atende às 3 da manhã, nos fins de semana, no feriado e não pede aumento.

Cálculo de ROI rápido para usar na conversa:
- Se o negócio recebe 100 leads por mês e converte 20%, são 20 vendas.
- Se o agente recuperar apenas 10% dos leads que não eram atendidos (outros 10 leads), com ticket médio de R$ 500, são R$ 5.000 a mais por mês.
- O agente custa menos que isso.

Use esse cálculo adaptado ao nicho do lead.""",
    },

    # -----------------------------------------------------------------------
    # CASES POR NICHO
    # -----------------------------------------------------------------------
    {
        "categoria": "nicho_clinica",
        "titulo": "Case: Clínicas e consultórios médicos",
        "content": """Clínicas perdem entre 3 e 5 pacientes por semana que mandam mensagem fora do horário e não recebem resposta.
Esses pacientes não ligam de volta. Vão para o concorrente.

O Agente 24 Horas para clínicas:
- Responde dúvidas sobre procedimentos e planos aceitos a qualquer hora
- Agenda consultas diretamente no Google Calendar ou sistema da clínica
- Envia lembretes automáticos de consulta (reduz no-show em até 40%)
- Qualifica se o paciente tem plano ou paga particular antes de chegar na recepção
- Avisa a secretaria quando um caso precisa de atenção urgente

Case real: clínica odontológica em São Paulo reduziu no-show de 35% para 12% em 60 dias com o agente enviando confirmações e lembretes automáticos.""",
    },
    {
        "categoria": "nicho_imobiliaria",
        "titulo": "Case: Imobiliárias e corretores",
        "content": """40% dos leads de imobiliária saem do anúncio e mandam mensagem fora do horário comercial.
Se o corretor não responder em menos de 5 minutos, a taxa de resposta cai 80%.

O Agente 24 Horas para imobiliárias:
- Responde na hora, qualquer horário, sobre imóveis disponíveis
- Qualifica o lead: tipo de imóvel, bairro, faixa de preço, entrada disponível, financiamento ou à vista
- Agenda visitas diretamente no calendário do corretor
- Filtra os curiosos dos compradores reais antes de chegar no corretor
- Envia fotos e informações do imóvel automaticamente

Case real: imobiliária com 3 corretores triplicou o número de visitas agendadas em 30 dias sem contratar mais corretores.""",
    },
    {
        "categoria": "nicho_ecommerce",
        "titulo": "Case: E-commerce e lojas online",
        "content": """E-commerces têm média de 70% de carrinhos abandonados. A maioria por dúvida não respondida.
Custo de aquisição de lead está entre R$ 15 e R$ 80. Perder o lead por falta de atendimento é jogar dinheiro fora.

O Agente 24 Horas para e-commerce:
- Responde dúvidas sobre tamanho, prazo, frete e trocas em tempo real
- Recupera carrinho abandonado com mensagem personalizada no WhatsApp
- Envia status de pedido automaticamente
- Lida com reclamações e solicitações de troca sem precisar do dono
- Faz upsell e cross-sell baseado no histórico de compra

Case real: loja de moda feminina recuperou R$ 18.000 em carrinhos abandonados no primeiro mês com o agente.""",
    },
    {
        "categoria": "nicho_restaurante",
        "titulo": "Case: Restaurantes, bares e delivery",
        "content": """Restaurantes perdem reservas todos os dias porque o telefone fica ocupado na hora do almoço.
Delivery perde pedido porque o cliente desiste de esperar alguém responder.

O Agente 24 Horas para restaurantes:
- Recebe reservas de mesa pelo WhatsApp, qualquer hora
- Responde sobre cardápio, opções sem glúten, sem lactose, veganismo
- Gerencia lista de espera e avisa quando a mesa libera
- Recebe pedidos de delivery e confirma tempo de entrega
- Envia promoções e cardápio do dia automaticamente

Case real: restaurante japonês em Florianópolis passou de 30 para 85 reservas por semana após o agente, sem mudar o cardápio nem contratar garçom.""",
    },
    {
        "categoria": "nicho_salao",
        "titulo": "Case: Salões de beleza e estética",
        "content": """Salões de beleza têm o telefone sempre ocupado. A profissional não pode parar o atendimento para responder WhatsApp.
Resultado: clientes vão pro concorrente que responde mais rápido.

O Agente 24 Horas para salões:
- Agenda horários automaticamente com base na disponibilidade real da agenda
- Responde sobre serviços, preços e duração
- Envia confirmação e lembrete 24h antes do horário
- Avisa sobre lista de espera para horários cheios
- Faz follow-up com clientes que não voltaram há mais de 30 dias

Case real: salão de estética em BH reduziu faltas de 8 por semana para 1 por semana com lembretes automáticos. Isso equivale a mais R$ 2.800 por mês recuperados.""",
    },
    {
        "categoria": "nicho_advocacia",
        "titulo": "Case: Escritórios de advocacia",
        "content": """Escritórios de advocacia perdem consultas iniciais porque o advogado não pode responder mensagens enquanto está em audiência.
Leads de advocacia são urgentes: quem tem um problema jurídico quer ajuda agora, não amanhã.

O Agente 24 Horas para advogados:
- Faz triagem inicial: área do direito, tipo de caso, urgência
- Qualifica se o caso é da especialidade do escritório
- Agenda consulta inicial sem expor a agenda do advogado
- Esclarece dúvidas gerais sem dar conselho jurídico
- Avisa o advogado imediatamente se chegar caso urgente (preso em flagrante, acidente, etc.)

Case real: advogado trabalhista em Curitiba passou a receber 12 consultas agendadas por semana contra 4 antes do agente, sem mudar o investimento em anúncio.""",
    },
    {
        "categoria": "nicho_educacao",
        "titulo": "Case: Cursos, escolas e mentorias",
        "content": """Infoprodutos e cursos têm pico de interesse no momento em que o lead vê o anúncio.
Se não responder em minutos, o interesse cai. O lead esquece.

O Agente 24 Horas para educação:
- Responde dúvidas sobre o curso, metodologia, duração, certificado
- Qualifica o perfil do aluno para entender se o produto é certo para ele
- Envia link de pagamento ou leva para a página de venda no momento certo
- Faz follow-up com quem não fechou ainda
- Responde sobre prazo de acesso, suporte, comunidade

Case real: mentoria de negócios com ticket de R$ 3.500 aumentou a taxa de fechamento de 8% para 23% em 45 dias ao responder leads no WhatsApp em menos de 1 minuto, qualquer hora.""",
    },
    {
        "categoria": "nicho_clinica_vet",
        "titulo": "Case: Clínicas veterinárias e petshops",
        "content": """Donos de pet são extremamente exigentes com tempo de resposta. Se o animal está mal, eles querem resposta imediata.
Clínicas que não respondem rápido perdem para o concorrente que tem plantão.

O Agente 24 Horas para veterinários:
- Triagem de urgência: o agente identifica se é caso de emergência e indica protocolo
- Agendamento de consultas e banho e tosa automaticamente
- Responde sobre vacinas, vermífugos, castrações e preços
- Envia lembretes de vacina e retorno
- Avisa sobre promoções de banho e tosa para fidelização

Case real: clínica vet em Goiânia aumentou agendamentos em 60% em 2 meses após o agente atender mensagens das 22h às 8h, horário em que a clínica estava fechada.""",
    },
    {
        "categoria": "nicho_financeiro",
        "titulo": "Case: Financeiras, correspondentes bancários e seguradoras",
        "content": """O mercado financeiro tem compliance rigoroso, mas a primeira resposta ao lead pode e deve ser automatizada.
Leads de crédito têm urgência: precisam do dinheiro logo.

O Agente 24 Horas para financeiras:
- Qualifica perfil de crédito sem dar análise (pergunta renda, objetivo, urgência)
- Explica produtos de forma clara sem comprometer conformidade
- Agenda ligação com o consultor no horário certo
- Faz follow-up com leads que pediram simulação mas não assinaram
- Responde dúvidas frequentes sobre documentação

Case real: correspondente bancário em Recife reduziu o tempo de resposta de leads de empréstimo de 4 horas para 40 segundos e dobrou a taxa de conversão para proposta em 30 dias.""",
    },

    # -----------------------------------------------------------------------
    # OBJEÇÕES
    # -----------------------------------------------------------------------
    {
        "categoria": "objecao",
        "titulo": "Objeção: parece robô, não tem a personalidade do meu negócio",
        "content": """Quando o lead disser que parece robô ou que o cliente vai perceber que não é humano, use:
"Você está conversando comigo agora. Pareceu robô?"
Se ele disser que não: "É exatamente assim que o agente do seu negócio vai funcionar. Treinamos com o seu tom de voz, suas expressões, seu jeito de atender."

Argumento técnico:
O agente é treinado com exemplos reais do negócio. O cliente pode definir o nome, o gênero, o tom (formal, descontraído, técnico). O agente não usa respostas genéricas. Cada mensagem é gerada com base no contexto da conversa.

Case de prova: clínica odontológica cujos pacientes não sabiam que eram atendidos por IA por 3 meses. Só descobriram quando a clínica divulgou.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: já tentei chatbot antes e não funcionou",
        "content": """Essa objeção é válida. A maioria dos chatbots anteriores eram fluxos de perguntas e respostas fixas.
Use: "Faz sentido, a maioria dos chatbots que existia era uma árvore de opções. Se o cliente saísse do script, travava. O Agente 24 Horas é diferente porque usa IA generativa: ele entende o que o cliente escreveu, pensa e responde, não segue um fluxo fixo. É a diferença entre um mapa de GPS antigo e o Waze de hoje."

Peça para ele descrever o que não funcionou antes. Isso mostra que você escuta e abre espaço para mostrar a diferença concreta.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: meu cliente não gosta de falar com máquina",
        "content": """Argumento direto:
"A maioria dos clientes não liga se quem respondeu é humano ou IA, desde que receba uma resposta rápida e útil. O que irrita o cliente não é a tecnologia, é esperar 4 horas para ouvir não sei te dizer, aguarda."

Dado de mercado: pesquisa da Zendesk mostra que 69% dos consumidores preferem resolver dúvidas simples com autoatendimento a esperar por um humano.

Reforce: o agente não substitui o humano para casos complexos. Ele resolve o simples para o humano focar no que importa.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: minha equipe já dá conta do atendimento",
        "content": """Não questione. Aprofunde:
"Que horas sua equipe para de responder?"
"O que acontece com as mensagens que chegam depois das 18h ou no fim de semana?"
"Quantas mensagens ficam sem resposta por dia em média?"

Se a equipe realmente dá conta, o agente libera eles para tarefas de maior valor. Nenhum atendente humano quer responder a mesma pergunta sobre preço 40 vezes por dia.

Reposicione: o agente não é concorrente da equipe. É o primeiro atendimento que qualifica e organiza para a equipe trabalhar melhor.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: não tenho dinheiro agora, momento ruim",
        "content": """Não force. Acolha:
"Entendo. Qual seria o momento ideal?"
Dependendo da resposta:
- Se for 1 ou 2 meses: mantenha o lead no CRM, agende follow-up.
- Se for vago: "O que eu posso te dizer é que a maioria dos clientes que adiou por causa do momento acabou falando que perdeu receita que pagaria o investimento várias vezes. Mas a decisão é sua e precisa fazer sentido pra você."

Nunca desconte nem desvalorize. Não reduza preço no WhatsApp.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: LGPD, segurança dos dados dos meus clientes",
        "content": """Resposta direta:
"Questão totalmente válida, especialmente para quem lida com saúde ou dados sensíveis."

Argumentos:
- Os dados ficam no servidor do próprio cliente (Supabase dedicado por conta, não compartilhado)
- Não vendemos nem compartilhamos dados com terceiros
- Você pode assinar um DPA (Data Processing Agreement) conosco
- O agente não armazena dados bancários nem de saúde sensíveis, apenas o histórico de conversa

Se o lead for da área médica ou jurídica, oferecer NDA e contrato específico.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objeção: preciso pensar, vou falar com meu sócio",
        "content": """Não pressione. Qualifique:
"Claro. O que você precisaria ver ou entender melhor antes de levar pro seu sócio?"
Isso revela a objeção real.

Se a objeção real vier, use o argumento correto.
Se não vier nada concreto, pergunte: "O que faria você sentir seguro o suficiente para tomar essa decisão?"

Ao encerrar: "Quando você acha que a gente consegue conversar de novo? Posso reservar um horário com o Gastão para você e seu sócio juntos se fizer sentido." """ ,
    },

    # -----------------------------------------------------------------------
    # DIFERENCIAIS E COMPARAÇÕES
    # -----------------------------------------------------------------------
    {
        "categoria": "diferencial",
        "titulo": "Por que o Agente 24 Horas é diferente de ChatGPT ou qualquer IA genérica",
        "content": """ChatGPT é uma IA genérica. Não sabe nada sobre o negócio do cliente.
O Agente 24 Horas é uma IA especialista no negócio específico do cliente.

Diferença prática:
- ChatGPT inventaria uma resposta sobre preço de procedimento. O Agente 24 Horas busca na base de conhecimento real e responde com o preço correto.
- ChatGPT não tem acesso à agenda. O Agente 24 Horas agenda diretamente.
- ChatGPT não lembra da conversa de ontem. O Agente 24 Horas lembra de tudo.
- ChatGPT não avisa o dono. O Agente 24 Horas notifica quando precisa de atenção humana.

É a diferença entre um médico generalista e um especialista no seu caso.""",
    },
    {
        "categoria": "diferencial",
        "titulo": "Diferenciais da DR.TRAFEGO frente a concorrentes",
        "content": """O mercado de agentes de IA para pequenas empresas está crescendo. Por que a DR.TRAFEGO?

1. Especialidade em tráfego pago: entendemos de onde vem o lead antes de atendê-lo. O agente é calibrado para o perfil do lead que vem de anúncio, não de indicação.
2. Treinamento com dados reais: usamos conversas reais do negócio do cliente, não templates genéricos.
3. Suporte humano real: o Gastão acompanha pessoalmente o período de calibração.
4. Resultado mensurável: entregamos relatório de conversas, leads qualificados, agendamentos realizados e taxa de resposta.
5. Sem contrato de fidelidade: o cliente fica porque funciona, não por multa.""",
    },
]


# ---------------------------------------------------------------------------
# Funcoes principais
# ---------------------------------------------------------------------------

def gerar_embedding(texto: str) -> list[float]:
    result = genai.embed_content(
        model=EMBED_MODEL,
        content=texto,
        task_type="RETRIEVAL_DOCUMENT",
    )
    return result["embedding"]


def inserir_documentos(docs: list[dict], supabase) -> None:
    total = len(docs)
    for i, doc in enumerate(docs, 1):
        conteudo = f"{doc['titulo']}\n\n{doc['content']}"
        print(f"[{i}/{total}] Gerando embedding: {doc['titulo'][:60]}...")

        embedding = gerar_embedding(conteudo)

        payload = {
            "content": conteudo,
            "metadata": {
                "titulo": doc["titulo"],
                "categoria": doc["categoria"],
            },
            "embedding": embedding,
        }

        supabase.table(TABLE).insert(payload).execute()
        print(f"         Inserido com sucesso.")
        time.sleep(DELAY_ENTRE_INSERTS)


def limpar_tabela(supabase) -> None:
    print(f"Apagando todos os documentos da tabela '{TABLE}'...")
    supabase.table(TABLE).delete().neq("id", 0).execute()
    print("Tabela limpa.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Popula a RAG do Agente 24 Horas.")
    parser.add_argument("--limpar", action="store_true", help="Apaga todos os documentos antes de inserir")
    parser.add_argument("--categoria", type=str, help="Insere apenas documentos de uma categoria especifica")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Erro: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY precisam estar no ambiente.")
        print("Exemplo: SUPABASE_URL=https://... SUPABASE_SERVICE_ROLE_KEY=... python scripts/seed_rag.py")
        sys.exit(1)

    if not GOOGLE_API_KEY:
        print("Erro: GOOGLE_API_KEY precisa estar no ambiente para gerar embeddings.")
        sys.exit(1)

    genai.configure(api_key=GOOGLE_API_KEY)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    if args.limpar:
        limpar_tabela(supabase)

    docs = DOCUMENTOS
    if args.categoria:
        docs = [d for d in DOCUMENTOS if d["categoria"] == args.categoria]
        if not docs:
            categorias = sorted({d["categoria"] for d in DOCUMENTOS})
            print(f"Categoria '{args.categoria}' nao encontrada.")
            print(f"Categorias disponiveis: {', '.join(categorias)}")
            sys.exit(1)

    print(f"\nInserindo {len(docs)} documento(s)...\n")
    inserir_documentos(docs, supabase)
    print(f"\nPronto. {len(docs)} documento(s) inserido(s) na tabela '{TABLE}'.")


if __name__ == "__main__":
    main()
