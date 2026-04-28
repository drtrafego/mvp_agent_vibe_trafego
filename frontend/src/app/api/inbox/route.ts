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
        last_msg.content    AS last_message,
        last_msg.role       AS last_role,
        COALESCE(last_msg.created_at, c.last_lead_msg_at, c.created_at) AS last_message_at
      FROM agente_trafego.contacts c
      LEFT JOIN LATERAL (
        SELECT content, role, created_at
        FROM agente_trafego.chat_sessions
        WHERE phone = c.phone
        ORDER BY created_at DESC
        LIMIT 1
      ) last_msg ON true
      WHERE c.phone IS NOT NULL
        AND (last_msg.content IS NOT NULL OR c.last_lead_msg_at IS NOT NULL)
      ORDER BY COALESCE(last_msg.created_at, c.last_lead_msg_at, c.created_at) DESC
      LIMIT 50
    `);

    return NextResponse.json(Array.from(rows));
  } catch (err) {
    console.error("GET /api/inbox error:", err);
    return NextResponse.json({ error: "Erro ao buscar conversas" }, { status: 500 });
  }
}
