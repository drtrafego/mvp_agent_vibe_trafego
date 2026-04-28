"use client";

import { useState } from "react";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";

interface BotToggleProps {
  contactId: string;
  initialBotActive: boolean;
  onToggle?: (botActive: boolean) => void;
}

export function BotToggle({ contactId, initialBotActive, onToggle }: BotToggleProps) {
  const [botActive, setBotActive] = useState(initialBotActive);
  const [loading, setLoading] = useState(false);

  async function handleToggle() {
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/inbox/${contactId}/bot-toggle`, { method: "PATCH" });
      if (res.ok) {
        const data = await res.json();
        setBotActive(data.botActive);
        onToggle?.(data.botActive);
      }
    } catch (err) {
      console.error("Erro ao alternar bot:", err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleToggle}
        disabled={loading}
        className={cn(
          "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all",
          botActive
            ? "bg-primary/15 text-primary hover:bg-primary/25"
            : "bg-orange-500/15 text-orange-500 hover:bg-orange-500/25",
          loading && "opacity-50 cursor-not-allowed"
        )}
      >
        {botActive ? (
          <>
            <Bot size={14} />
            Bot ativo
          </>
        ) : (
          <>
            <User size={14} />
            Modo humano
          </>
        )}
      </button>

      <button
        onClick={handleToggle}
        disabled={loading}
        aria-label="Alternar bot"
        className={cn(
          "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
          botActive ? "bg-primary" : "bg-orange-500",
          loading && "opacity-50 cursor-not-allowed"
        )}
      >
        <span
          className={cn(
            "inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform",
            botActive ? "translate-x-5" : "translate-x-1"
          )}
        />
      </button>
    </div>
  );
}
