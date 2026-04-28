import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const META_ACCESS_TOKEN = process.env.META_ACCESS_TOKEN ?? "";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ mediaId: string }> }
) {
  const { mediaId } = await params;

  if (!META_ACCESS_TOKEN) {
    return NextResponse.json({ error: "Token não configurado" }, { status: 500 });
  }

  try {
    // Passo 1: busca a URL de download da mídia
    const metaResp = await fetch(
      `https://graph.facebook.com/v20.0/${mediaId}`,
      { headers: { Authorization: `Bearer ${META_ACCESS_TOKEN}` } }
    );

    if (!metaResp.ok) {
      return NextResponse.json({ error: "Mídia não encontrada" }, { status: 404 });
    }

    const { url } = await metaResp.json();
    if (!url) {
      return NextResponse.json({ error: "URL de mídia indisponível" }, { status: 404 });
    }

    // Passo 2: faz download do arquivo de áudio
    const audioResp = await fetch(url, {
      headers: { Authorization: `Bearer ${META_ACCESS_TOKEN}` },
    });

    if (!audioResp.ok) {
      return NextResponse.json({ error: "Falha ao baixar áudio" }, { status: 502 });
    }

    const contentType = audioResp.headers.get("content-type") ?? "audio/ogg";
    const buffer = await audioResp.arrayBuffer();

    return new Response(buffer, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch (err) {
    console.error("GET /api/inbox/media/[mediaId] error:", err);
    return NextResponse.json({ error: "Erro interno" }, { status: 500 });
  }
}
