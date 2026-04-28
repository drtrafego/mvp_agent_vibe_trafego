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

const AVATAR_COLORS = [
  "bg-indigo-600",
  "bg-purple-600",
  "bg-pink-600",
  "bg-emerald-600",
  "bg-amber-600",
  "bg-sky-600",
];

function getAvatarColor(str: string) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
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

export function ConversationList({
  initialConversations,
}: ConversationListProps) {
  const [conversations, setConversations] =
    useState<ConversationSummary[]>(initialConversations);
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
    <aside className="flex w-full md:w-80 md:shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
      {/* Header */}
      <div className="border-b border-zinc-800 px-4 py-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            WhatsApp Inbox
          </h2>
          <button
            onClick={() => refresh(false)}
            disabled={refreshing}
            className="flex items-center justify-center h-6 w-6 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
            title="Atualizar conversas"
          >
            <RefreshCw
              size={13}
              className={refreshing ? "animate-spin" : ""}
            />
          </button>
        </div>
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar conversa..."
            className="w-full rounded-lg bg-zinc-800 py-2 pl-8 pr-3 text-xs text-zinc-300 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-600"
          />
        </div>
      </div>

      {/* Lista */}
      <div className="flex-1 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-xs text-zinc-600">
            {search ? "Nenhuma conversa encontrada" : "Nenhuma conversa ainda"}
          </p>
        ) : (
          filtered.map((conv) => {
            const isActive = conv.id === activeId;
            const displayName = conv.name || conv.phone || "Lead";
            const initials = displayName
              .split(" ")
              .slice(0, 2)
              .map((n) => n[0])
              .join("")
              .toUpperCase();
            const avatarColor = getAvatarColor(conv.id);

            return (
              <Link key={conv.id} href={`/inbox/${conv.id}`}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-3 transition-colors cursor-pointer",
                    isActive ? "bg-zinc-800" : "hover:bg-zinc-800/60"
                  )}
                >
                  <div
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white",
                      avatarColor
                    )}
                  >
                    {initials}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate text-sm font-medium text-zinc-300">
                        {displayName}
                      </span>
                      <span className="shrink-0 text-[10px] text-zinc-600">
                        {timeAgo(conv.last_message_at)}
                      </span>
                    </div>

                    <div className="flex items-center justify-between gap-1 mt-0.5">
                      <span className="truncate text-xs text-zinc-500">
                        {conv.last_role === "assistant" ? "Bot: " : ""}
                        {conv.last_message || "Sem mensagens"}
                      </span>

                      <div className="flex shrink-0 items-center gap-1">
                        {conv.bot_active ? (
                          <Bot size={11} className="text-indigo-400" title="Bot ativo" />
                        ) : (
                          <User size={11} className="text-orange-400" title="Modo humano" />
                        )}
                      </div>
                    </div>
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
