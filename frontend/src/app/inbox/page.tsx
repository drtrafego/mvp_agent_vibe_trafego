export const dynamic = "force-dynamic";

import { MessageSquare } from "lucide-react";
import { db } from "@/db";
import { sql } from "drizzle-orm";
import { ConversationList } from "@/components/inbox/ConversationList";

async function getConversations() {
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
      FROM agente_trafego.contacts c
      INNER JOIN LATERAL (
        SELECT content, role, created_at
        FROM agente_trafego.chat_sessions
        WHERE phone = c.phone
        ORDER BY created_at DESC
        LIMIT 1
      ) last_msg ON true
      ORDER BY last_msg.created_at DESC
      LIMIT 50
    `);
    return Array.from(rows) as never[];
  } catch {
    return [];
  }
}

export default async function InboxPage() {
  const conversations = await getConversations();

  return (
    <div className="flex h-full">
      <ConversationList initialConversations={conversations} />

      {/* Área vazia no desktop */}
      <div className="hidden md:flex flex-1 items-center justify-center bg-zinc-950">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-800/50">
            <MessageSquare size={28} className="text-zinc-500" />
          </div>
          <p className="text-sm font-medium text-zinc-400">Selecione uma conversa</p>
          <p className="mt-1 text-xs text-zinc-600">
            Escolha um lead na lista ao lado
          </p>
        </div>
      </div>
    </div>
  );
}
