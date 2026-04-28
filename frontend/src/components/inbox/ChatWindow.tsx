"use client";

import { useState, useEffect, useRef } from "react";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import Link from "next/link";
import { BotToggle } from "./BotToggle";
import { MessageList } from "./MessageBubble";

interface ChatMessage {
  role: string;
  content: string;
  created_at: string;
}

interface ConversationSummary {
  id: string;
  name: string | null;
  phone: string | null;
  bot_active: boolean;
  stage: string | null;
  temperature: string | null;
}

interface ChatWindowProps {
  contact: ConversationSummary;
  initialMessages: ChatMessage[];
}

export function ChatWindow({ contact, initialMessages }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [botActive, setBotActive] = useState(contact.bot_active);
  const [refreshing, setRefreshing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function refresh() {
    setRefreshing(true);
    try {
      const res = await fetch(`/api/inbox/${contact.id}/messages`);
      if (res.ok) {
        const data: ChatMessage[] = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-refresh a cada 30s
  useEffect(() => {
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact.id]);

  const displayName = contact.name || contact.phone || "Lead";

  return (
    <div className="flex flex-col h-full w-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-card shrink-0">
        <div className="flex items-center gap-3">
          <Link
            href="/inbox"
            className="md:hidden flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Voltar"
          >
            <ArrowLeft size={18} />
          </Link>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground shrink-0">
            {displayName[0].toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-medium">{displayName}</p>
            {contact.phone && <p className="text-xs text-muted-foreground">{contact.phone}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center justify-center h-7 w-7 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-40"
            title="Atualizar mensagens"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          </button>
          <BotToggle contactId={contact.id} initialBotActive={botActive} onToggle={setBotActive} />
        </div>
      </div>

      {/* Banner modo humano */}
      {!botActive && (
        <div className="flex items-center gap-2 bg-orange-500/10 border-b border-orange-500/20 px-4 py-2 shrink-0">
          <AlertTriangle size={14} className="text-orange-500" />
          <span className="text-xs text-orange-500">Atendimento humano ativo — bot pausado</span>
        </div>
      )}

      {/* Mensagens */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <MessageList messages={messages} />
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
