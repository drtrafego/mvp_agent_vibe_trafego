import logging

from google import genai
from google.genai import types
from supabase import create_client, Client

from config.settings import settings

logger = logging.getLogger(__name__)

_supabase: Client | None = None
_genai_client: genai.Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def _get_genai() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _genai_client


async def search_knowledge(query: str, top_k: int = 4) -> str:
    """Busca documentos relevantes na base RAG. Retorna conteudo concatenado."""
    try:
        embed_result = await _get_genai().aio.models.embed_content(
            model="text-embedding-004",
            contents=query,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        embedding_vector: list[float] = embed_result.embeddings[0].values

        supabase = _get_supabase()

        try:
            result = supabase.rpc(
                "match_documents",
                {
                    "query_embedding": embedding_vector,
                    "match_threshold": 0.7,
                    "match_count": top_k,
                },
            ).execute()
            rows = result.data or []
        except Exception as rpc_err:
            logger.warning("match_documents RPC falhou, tentando select direto: %s", rpc_err)
            vec_str = "[" + ",".join(str(v) for v in embedding_vector) + "]"
            result = (
                supabase.table("documents")
                .select("content, metadata")
                .order(f"embedding <=> '{vec_str}'::vector")
                .limit(top_k)
                .execute()
            )
            rows = result.data or []

        if not rows:
            return "Nenhum documento relevante encontrado na base de conhecimento."

        contents = [row.get("content", "") for row in rows if row.get("content")]
        return "\n---\n".join(contents)

    except Exception as exc:
        logger.error("Erro ao buscar RAG: %s", exc)
        return "Nenhum documento relevante encontrado na base de conhecimento."
