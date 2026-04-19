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
    # PRODUTO / O QUE E O AGENTE 24 HORAS
    # -----------------------------------------------------------------------
    {
        "categoria": "produto",
        "titulo": "O que e o Agente 24 Horas",
        "content": """O Agente 24 Horas e um atendente de IA treinado especificamente para o negocio do cliente.
Ele responde no WhatsApp em tempo real, 24 horas por dia, 7 dias por semana, sem precisar de humano.
Entende audio, texto e contexto da conversa. Lembra de tudo que o cliente ja disse.
Pode agendar, qualificar leads, responder duvidas, fazer follow-up automatico e avisar o dono quando algo precisa de atencao humana.
Nao e um chatbot de respostas prontas. E um agente que raciocina, usa ferramentas e toma decisoes como um atendente treinado.
A diferenca para um chatbot comum: o Agente 24 Horas entende contexto, nao so palavras-chave. Se o cliente perguntar algo fora do script, ele responde com inteligencia, nao trava.""",
    },
    {
        "categoria": "produto",
        "titulo": "Como e entregue o Agente 24 Horas",
        "content": """A entrega e feita em 3 etapas:
1. Reuniao de onboarding: o Gastao mapeia o negocio, os principais fluxos de atendimento, objecoes mais comuns e o tom de voz da marca.
2. Configuracao e treinamento: a equipe monta a base de conhecimento do agente com as informacoes do cliente, integra ao WhatsApp Business e ajusta o comportamento.
3. Periodo de calibracao: nas primeiras 2 semanas, o cliente reporta ajustes e o agente e refinado ate estar perfeito.

Prazo medio de entrega: 7 a 14 dias uteis apos o onboarding.
O cliente nao precisa saber programar. A gestao e feita pela equipe DR.TRAFEGO.""",
    },
    {
        "categoria": "produto",
        "titulo": "Integracoes disponiveis",
        "content": """O Agente 24 Horas integra com:
- WhatsApp Business API (Meta oficial)
- Google Calendar (agendamento automatico)
- Google Sheets (registro de leads)
- CRM via webhook (qualquer sistema com API)
- Sistemas de agendamento: Calendly, AgendaPro, Doctoralia (sob consulta)
- Instagram Direct (roadmap)

Nao precisa trocar de sistema. O agente se conecta ao que o cliente ja usa.""",
    },
    {
        "categoria": "produto",
        "titulo": "Seguranca e LGPD",
        "content": """O Agente 24 Horas e construido sobre infraestrutura segura:
- Dados armazenados em servidores certificados (Supabase, infra AWS us-east)
- Nenhuma conversa e compartilhada com terceiros
- Conformidade com LGPD: dados do cliente sao usados exclusivamente para operar o agente dele
- Possibilidade de contrato de confidencialidade (NDA) para segmentos sensiveis (saude, juridico, financeiro)
- O cliente pode solicitar exclusao de dados a qualquer momento

A IA nao toma decisoes financeiras nem envia dados bancarios. Toda transacao financeira e redirecionada para o humano.""",
    },

    # -----------------------------------------------------------------------
    # PRECO E INVESTIMENTO
    # -----------------------------------------------------------------------
    {
        "categoria": "preco",
        "titulo": "Como responder sobre preco antes do valor estar construido",
        "content": """Quando o lead perguntar preco antes de entender o valor, use a virada de preco:
"Antes de falar em numero, deixa eu entender melhor o seu caso para garantir que faz sentido pra voce."
Depois entregue o pedaco do queijo do nicho dele.

Se insistir muito, diga:
"O investimento varia de acordo com o volume de atendimentos e as integracoes necessarias. O Gastao monta uma proposta customizada na call. O que posso te dizer e que clientes com volume similar ao seu costumam recuperar o investimento nos primeiros 60 dias so com os leads que paravam de responder fora do horario."

Nunca de numero sem contexto. Preco sem valor percebido e sempre caro.""",
    },
    {
        "categoria": "preco",
        "titulo": "Posicionamento de valor do Agente 24 Horas",
        "content": """O Agente 24 Horas nao compete com funcionario. Compete com o custo de nao atender.
Um funcionario de atendimento custa entre R$ 2.000 e R$ 4.000 por mes com encargos, so atende em horario comercial e tira ferias.
O Agente 24 Horas atende as 3 da manha, nos fins de semana, no feriado e nao pede aumento.

Calculo de ROI rapido para usar na conversa:
- Se o negocio recebe 100 leads por mes e converte 20%, sao 20 vendas.
- Se o agente recuperar apenas 10% dos leads que nao eram atendidos (outros 10 leads), com ticket medio de R$ 500, sao R$ 5.000 a mais por mes.
- O agente custa menos que isso.

Use esse calculo adaptado ao nicho do lead.""",
    },

    # -----------------------------------------------------------------------
    # CASES POR NICHO
    # -----------------------------------------------------------------------
    {
        "categoria": "nicho_clinica",
        "titulo": "Case: Clinicas e consultórios medicos",
        "content": """Clinicas perdem entre 3 e 5 pacientes por semana que mandam mensagem fora do horario e nao recebem resposta.
Esses pacientes nao ligam de volta. Vao para o concorrente.

O Agente 24 Horas para clinicas:
- Responde duvidas sobre procedimentos e planos aceitos a qualquer hora
- Agenda consultas diretamente no Google Calendar ou sistema da clinica
- Envia lembretes automaticos de consulta (reduz no-show em ate 40%)
- Qualifica se o paciente tem plano ou paga particular antes de chegar na recepcao
- Avisa a secretaria quando um caso precisa de atencao urgente

Case real: clinica odontologica em Sao Paulo reduziu no-show de 35% para 12% em 60 dias com o agente enviando confirmacoes e lembretes automaticos.""",
    },
    {
        "categoria": "nicho_imobiliaria",
        "titulo": "Case: Imobiliarias e corretores",
        "content": """40% dos leads de imobiliaria saem do anuncio e mandam mensagem fora do horario comercial.
Se o corretor nao responder em menos de 5 minutos, a taxa de resposta cai 80%.

O Agente 24 Horas para imobiliarias:
- Responde na hora, qualquer horario, sobre imoveis disponiveis
- Qualifica o lead: tipo de imovel, bairro, faixa de preco, entrada disponivel, financiamento ou a vista
- Agenda visitas diretamente no calendario do corretor
- Filtra os curiosos dos compradores reais antes de chegar no corretor
- Envia fotos e informacoes do imovel automaticamente

Case real: imobiliaria com 3 corretores triplicou o numero de visitas agendadas em 30 dias sem contratar mais corretores.""",
    },
    {
        "categoria": "nicho_ecommerce",
        "titulo": "Case: E-commerce e lojas online",
        "content": """E-commerces tem media de 70% de carrinhos abandonados. A maioria por duvida nao respondida.
Custo de aquisicao de lead esta entre R$ 15 e R$ 80. Perder o lead por falta de atendimento e jogar dinheiro fora.

O Agente 24 Horas para e-commerce:
- Responde duvidas sobre tamanho, prazo, frete e trocas em tempo real
- Recupera carrinho abandonado com mensagem personalizada no WhatsApp
- Envia status de pedido automaticamente
- Lida com reclamacoes e solicitacoes de troca sem precisar do dono
- Faz upsell e cross-sell baseado no historico de compra

Case real: loja de moda feminina recuperou R$ 18.000 em carrinhos abandonados no primeiro mes com o agente.""",
    },
    {
        "categoria": "nicho_restaurante",
        "titulo": "Case: Restaurantes, bares e delivery",
        "content": """Restaurantes perdem reservas todos os dias porque o telefone fica ocupado na hora do almoco.
Delivery perde pedido porque o cliente desiste de esperar alguem responder.

O Agente 24 Horas para restaurantes:
- Recebe reservas de mesa pelo WhatsApp, qualquer hora
- Responde sobre cardapio, opcoes sem gluten, sem lactose, veganismo
- Gerencia lista de espera e avisa quando a mesa libera
- Recebe pedidos de delivery e confirma tempo de entrega
- Envia promocoes e cardapio do dia automaticamente

Case real: restaurante japones em Florianopolis passou de 30 para 85 reservas por semana apos o agente, sem mudar o cardapio nem contratar garcom.""",
    },
    {
        "categoria": "nicho_salao",
        "titulo": "Case: Saloes de beleza e estetica",
        "content": """Saloes de beleza tem o telefone sempre ocupado. A profissional nao pode parar o atendimento para responder WhatsApp.
Resultado: clientes vao pro concorrente que responde mais rapido.

O Agente 24 Horas para saloes:
- Agenda horarios automaticamente com base na disponibilidade real da agenda
- Responde sobre servicos, precos e duracao
- Envia confirmacao e lembrete 24h antes do horario
- Avisa sobre lista de espera para horarios cheios
- Faz follow-up com clientes que nao voltaram ha mais de 30 dias

Case real: salao de estetica em BH reduziu faltas de 8 por semana para 1 por semana com lembretes automaticos. Isso equivale a mais R$ 2.800 por mes recuperados.""",
    },
    {
        "categoria": "nicho_advocacia",
        "titulo": "Case: Escritorios de advocacia",
        "content": """Escritorios de advocacia perdem consultas iniciais porque o advogado nao pode responder mensagens enquanto esta em audiencia.
Leads de advocacia sao urgentes: quem tem um problema juridico quer ajuda agora, nao amanha.

O Agente 24 Horas para advogados:
- Faz triagem inicial: area do direito, tipo de caso, urgencia
- Qualifica se o caso e da especialidade do escritorio
- Agenda consulta inicial sem expor a agenda do advogado
- Esclarece duvidas gerais sem dar conselho juridico
- Avisa o advogado imediatamente se chegar caso urgente (preso em flagrante, acidente, etc.)

Case real: advogado trabalhista em Curitiba passou a receber 12 consultas agendadas por semana contra 4 antes do agente, sem mudar o investimento em anuncio.""",
    },
    {
        "categoria": "nicho_educacao",
        "titulo": "Case: Cursos, escolas e mentorias",
        "content": """Infoprodutos e cursos tem pico de interesse no momento em que o lead ve o anuncio.
Se nao responder em minutos, o interesse cai. O lead esquece.

O Agente 24 Horas para educacao:
- Responde duvidas sobre o curso, metodologia, duracao, certificado
- Qualifica o perfil do aluno para entender se o produto e certo para ele
- Envia link de pagamento ou leva para a pagina de venda no momento certo
- Faz follow-up com quem nao fechou ainda
- Responde sobre prazo de acesso, suporte, comunidade

Case real: mentoria de negocios com ticket de R$ 3.500 aumentou a taxa de fechamento de 8% para 23% em 45 dias ao responder leads no WhatsApp em menos de 1 minuto, qualquer hora.""",
    },
    {
        "categoria": "nicho_clinica_vet",
        "titulo": "Case: Clinicas veterinarias e petshops",
        "content": """Donos de pet sao extremamente exigentes com tempo de resposta. Se o animal esta mal, eles querem resposta imediata.
Clinicas que nao respondem rapido perdem para o concorrente que tem plantao.

O Agente 24 Horas para veterinarios:
- Triagem de urgencia: o agente identifica se e caso de emergencia e indica protocolo
- Agendamento de consultas e banho e tosa automaticamente
- Responde sobre vacinas, vermifugos, castracoes e precos
- Envia lembretes de vacina e retorno
- Avisa sobre promocoes de banho e tosa para fidelizacao

Case real: clinica vet em Goiania aumentou agendamentos em 60% em 2 meses apos o agente atender mensagens das 22h as 8h, horario em que a clinica estava fechada.""",
    },
    {
        "categoria": "nicho_financeiro",
        "titulo": "Case: Financeiras, correspondentes bancarios e seguradoras",
        "content": """O mercado financeiro tem compliance rigoroso, mas a primeira resposta ao lead pode e deve ser automatizada.
Leads de credito tem urgencia: precisam do dinheiro logo.

O Agente 24 Horas para financeiras:
- Qualifica perfil de credito sem dar analise (pergunta renda, objetivo, urgencia)
- Explica produtos de forma clara sem comprometer conformidade
- Agenda ligacao com o consultor no horario certo
- Faz follow-up com leads que pediram simulacao mas nao assinaram
- Responde duvidas frequentes sobre documentacao

Case real: correspondente bancario em Recife reduziu o tempo de resposta de leads de emprestimo de 4 horas para 40 segundos e dobrou a taxa de conversao para proposta em 30 dias.""",
    },

    # -----------------------------------------------------------------------
    # OBJECOES
    # -----------------------------------------------------------------------
    {
        "categoria": "objecao",
        "titulo": "Objecao: parece robo, nao tem a personalidade do meu negocio",
        "content": """Quando o lead disser que parece robo ou que o cliente vai perceber que nao e humano, use:
"Voce esta conversando comigo agora. Pareceu robo?"
Se ele disser que nao: "E exatamente assim que o agente do seu negocio vai funcionar. Treinamos com o seu tom de voz, suas expressoes, seu jeito de atender."

Argumento tecnico:
O agente e treinado com exemplos reais do negocio. O cliente pode definir o nome, o genero, o tom (formal, descontraido, tecnico). O agente nao usa respostas genericas. Cada mensagem e gerada com base no contexto da conversa.

Case de prova: clinica odontologica cujos pacientes nao sabiam que eram atendidos por IA por 3 meses. So descobriram quando a clinica divulgou.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: ja tentei chatbot antes e nao funcionou",
        "content": """Essa objecao e valida. A maioria dos chatbots anteriores eram fluxos de perguntas e respostas fixas.
Use: "Faz sentido, a maioria dos chatbots que existia era uma arvore de opcoes. Se o cliente saisse do script, travava. O Agente 24 Horas e diferente porque usa IA generativa: ele entende o que o cliente escreveu, pensa e responde, nao segue um fluxo fixo. E a diferenca entre um mapa de GPS antigo e o Waze de hoje."

Peca para ele descrever o que nao funcionou antes. Isso mostra que voce escuta e abre espaco para mostrar a diferenca concreta.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: meu cliente nao gosta de falar com maquina",
        "content": """Argumento direto:
"A maioria dos clientes nao liga se quem respondeu e humano ou IA, desde que receba uma resposta rapida e util. O que irrita o cliente nao e a tecnologia, e esperar 4 horas para ouvir nao sei te dizer, aguarda."

Dado de mercado: pesquisa da Zendesk mostra que 69% dos consumidores preferem resolver duvidas simples com autoatendimento a esperar por um humano.

Reforce: o agente nao substitui o humano para casos complexos. Ele resolve o simples para o humano focar no que importa.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: minha equipe ja da conta do atendimento",
        "content": """Nao questione. Aprofunde:
"Que horas sua equipe para de responder?"
"O que acontece com as mensagens que chegam depois das 18h ou no fim de semana?"
"Quantas mensagens ficam sem resposta por dia em media?"

Se a equipe realmente da conta, o agente libera eles para tarefas de maior valor. Nenhum atendente humano quer responder a mesma pergunta sobre preco 40 vezes por dia.

Reposicione: o agente nao e concorrente da equipe. E o primeiro atendimento que qualifica e organiza para a equipe trabalhar melhor.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: nao tenho dinheiro agora, momento ruim",
        "content": """Nao force. Acolha:
"Entendo. Qual seria o momento ideal?"
Dependendo da resposta:
- Se for 1 ou 2 meses: mantenha o lead no CRM, agende follow-up.
- Se for vago: "O que eu posso te dizer e que a maioria dos clientes que adiou por causa do momento acabou falando que perdeu receita que pagaria o investimento varias vezes. Mas a decisao e sua e precisa fazer sentido pra voce."

Nunca desconte nem desvalorize. Nao reduza preco no WhatsApp.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: LGPD, seguranca dos dados dos meus clientes",
        "content": """Resposta direta:
"Questao totalmente valida, especialmente para quem lida com saude ou dados sensiveis."

Argumentos:
- Os dados ficam no servidor do proprio cliente (Supabase dedicado por conta, nao compartilhado)
- Nao vendemos nem compartilhamos dados com terceiros
- Voce pode assinar um DPA (Data Processing Agreement) conosco
- O agente nao armazena dados bancarios nem de saude sensiveis, apenas o historico de conversa

Se o lead for da area medica ou juridica, oferecer NDA e contrato especifico.""",
    },
    {
        "categoria": "objecao",
        "titulo": "Objecao: preciso pensar, vou falar com meu socio",
        "content": """Nao pressione. Qualifique:
"Claro. O que voce precisaria ver ou entender melhor antes de levar pro seu socio?"
Isso revela a objecao real.

Se a objecao real vier, use o argumento correto.
Se nao vier nada concreto, pergunte: "O que faria voce sentir seguro o suficiente para tomar essa decisao?"

Ao encerrar: "Quando voce acha que a gente consegue conversar de novo? Posso reservar um horario com o Gastao para voce e seu socio juntos se fizer sentido." """ ,
    },

    # -----------------------------------------------------------------------
    # DIFERENCIAIS E COMPARACOES
    # -----------------------------------------------------------------------
    {
        "categoria": "diferencial",
        "titulo": "Por que o Agente 24 Horas e diferente de ChatGPT ou qualquer IA generica",
        "content": """ChatGPT e uma IA generica. Nao sabe nada sobre o negocio do cliente.
O Agente 24 Horas e uma IA especialista no negocio especifico do cliente.

Diferenca pratica:
- ChatGPT inventaria uma resposta sobre preco de procedimento. O Agente 24 Horas busca na base de conhecimento real e responde com o preco correto.
- ChatGPT nao tem acesso a agenda. O Agente 24 Horas agenda diretamente.
- ChatGPT nao lembra da conversa de ontem. O Agente 24 Horas lembra de tudo.
- ChatGPT nao avisa o dono. O Agente 24 Horas notifica quando precisa de atencao humana.

E a diferenca entre um medico generalista e um especialista no seu caso.""",
    },
    {
        "categoria": "diferencial",
        "titulo": "Diferenciais da DR.TRAFEGO frente a concorrentes",
        "content": """O mercado de agentes de IA para pequenas empresas esta crescendo. Por que a DR.TRAFEGO?

1. Especialidade em trafego pago: entendemos de onde vem o lead antes de atende-lo. O agente e calibrado para o perfil do lead que vem de anuncio, nao de indicacao.
2. Treinamento com dados reais: usamos conversas reais do negocio do cliente, nao templates genericos.
3. Suporte humano real: o Gastao acompanha pessoalmente o periodo de calibracao.
4. Resultado mensuravel: entregamos relatorio de conversas, leads qualificados, agendamentos realizados e taxa de resposta.
5. Sem contrato de fidelidade: o cliente fica porque funciona, nao por multa.""",
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
