"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, RefreshCw, Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";

interface ConversationSummary {
  id: string;
  name: string | null;
  phone: string | null;
  bot_active: boolean;
  stage: string | null;
  temperature: string | null;
  last_message: string | null;
  last_role: string | null;
  last_message_at: string;
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}

interface ConversationListProps {
  initialConversations: ConversationSummary[];
}

export function ConversationList({ initialConversations }: ConversationListProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>(initialConversations);
  const [search, setSearch] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const pathname = usePathname();

  const refresh = useCallback(async (silent = true) => {
    if (!silent) setRefreshing(true);
    try {
      const res = await fetch("/api/inbox");
      if (res.ok) setConversations(await res.json());
    } catch {
      // silencioso
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = setInterval(() => refresh(true), 60_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const activeId = pathname.split("/inbox/")[1] || "";

  const filtered = conversations.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      c.name?.toLowerCase().includes(q) ||
      c.phone?.includes(q) ||
      c.last_message?.toLowerCase().includes(q)
    );
  });

  return (
    <aside className="flex w-full md:w-80 md:shrink-0 flex-col border-r bg-card">
      {/* Header */}
      <div className="border-b px-4 py-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold">WhatsApp Inbox</h2>
          <button
            onClick={() => refresh(false)}
            disabled={refreshing}
            className="flex items-center justify-center h-6 w-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-40"
            title="Atualizar conversas"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar conversa..."
            className="w-full rounded-lg border bg-background py-2 pl-8 pr-3 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {/* Lista */}
      <div className="flex-1 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground">
            {search ? "Nenhuma conversa encontrada" : "Nenhuma conversa ainda"}
          </p>
        ) : (
          filtered.map((conv) => {
            const isActive = conv.id === activeId;
            const displayName = conv.name || conv.phone || "Lead";
            return (
              <Link
                key={conv.id}
                href={`/inbox/${conv.id}`}
                className={cn(
                  "flex items-start gap-3 rounded-lg p-3 transition-colors",
                  isActive ? "bg-accent" : "hover:bg-muted/50"
                )}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {displayName[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium">{displayName}</p>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {timeAgo(conv.last_message_at)}
                    </span>
                  </div>
                  {conv.last_message && (
                    <p className="truncate text-xs text-muted-foreground mt-0.5">
                      {conv.last_role === "assistant" ? "Bot: " : ""}
                      {conv.last_message}
                    </p>
                  )}
                  <div className="flex items-center gap-1 mt-1">
                    {conv.bot_active ? (
                      <span className="flex items-center gap-0.5 text-[10px] text-primary">
                        <Bot size={10} /> ativo
                      </span>
                    ) : (
                      <span className="flex items-center gap-0.5 text-[10px] text-orange-500">
                        <User size={10} /> humano
                      </span>
                    )}
                    {conv.stage && (
                      <span className="text-[10px] text-muted-foreground">&middot; {conv.stage}</span>
                    )}
                  </div>
                </div>
              </Link>
            );
          })
        )}
      </div>
    </aside>
  );
}
