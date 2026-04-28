import { NextResponse } from "next/server";
import { db } from "@/db";
import { contacts } from "@/db/schema";
import { eq } from "drizzle-orm";
import { sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ contactId: string }> }
) {
  const { contactId } = await params;

  const [contact] = await db.select({ phone: contacts.phone }).from(contacts).where(eq(contacts.id, contactId));
  if (!contact?.phone) {
    return NextResponse.json({ error: "Contato não encontrado" }, { status: 404 });
  }

  try {
    const rows = await db.execute(sql`
      SELECT role, content, message_type, media_id, created_at
      FROM agente_vibe.chat_sessions
      WHERE phone = ${contact.phone}
      ORDER BY created_at ASC
      LIMIT 200
    `);

    return NextResponse.json(Array.from(rows));
  } catch (err) {
    console.error("GET /api/inbox/[contactId]/messages error:", err);
    return NextResponse.json({ error: "Erro ao buscar mensagens" }, { status: 500 });
  }
}
