import { NextResponse } from "next/server";
import { db } from "@/db";
import { sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const rows = await db.execute(sql`
      SELECT
        c.id,
        c.name,
        c.phone,
        c.bot_active,
        c.stage,
        c.temperature,
        last_msg.content  AS last_message,
        last_msg.role     AS last_role,
        last_msg.created_at AS last_message_at
      FROM agente_vibe.contacts c
      INNER JOIN LATERAL (
        SELECT content, role, created_at
        FROM agente_vibe.chat_sessions
        WHERE phone = c.phone
        ORDER BY created_at DESC
        LIMIT 1
      ) last_msg ON true
      ORDER BY last_msg.created_at DESC
      LIMIT 50
    `);

    return NextResponse.json(Array.from(rows));
  } catch (err) {
    console.error("GET /api/inbox error:", err);
    return NextResponse.json({ error: "Erro ao buscar conversas" }, { status: 500 });
  }
}
