export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { db } from "@/db";
import { contacts } from "@/db/schema";
import { eq } from "drizzle-orm";
import { sql } from "drizzle-orm";
import { ConversationList } from "@/components/inbox/ConversationList";
import { ChatWindow } from "@/components/inbox/ChatWindow";

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

export default async function InboxChatPage({
  params,
}: {
  params: Promise<{ contactId: string }>;
}) {
  const { contactId } = await params;

  const [contact] = await db
    .select({
      id: contacts.id,
      name: contacts.name,
      phone: contacts.phone,
      bot_active: contacts.botActive,
      stage: contacts.stage,
      temperature: contacts.temperature,
    })
    .from(contacts)
    .where(eq(contacts.id, contactId));

  if (!contact) notFound();

  let initialMessages: { role: string; content: string; created_at: string }[] = [];
  if (contact.phone) {
    try {
      const rows = await db.execute(sql`
        SELECT role, content, created_at
        FROM agente_trafego.chat_sessions
        WHERE phone = ${contact.phone}
        ORDER BY created_at ASC
        LIMIT 200
      `);
      initialMessages = Array.from(rows) as typeof initialMessages;
    } catch {
      // retorna vazio
    }
  }

  const allConversations = await getConversations();

  return (
    <div className="flex h-full">
      {/* Lista - oculta no mobile */}
      <div className="hidden md:flex md:w-80 md:shrink-0">
        <ConversationList initialConversations={allConversations} />
      </div>

      {/* Chat */}
      <div className="flex flex-1 overflow-hidden">
        <ChatWindow contact={contact} initialMessages={initialMessages} />
      </div>
    </div>
  );
}
