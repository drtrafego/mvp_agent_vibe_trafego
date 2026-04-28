"use client";

import { cn } from "@/lib/utils";

export interface ChatMessage {
  role: string;
  content: string;
  created_at: string;
}

function formatTime(dateStr: string) {
  return new Date(dateStr).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateSeparator(dateStr: string) {
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return "Hoje";
  if (d.toDateString() === yesterday.toDateString()) return "Ontem";
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function toDateKey(dateStr: string) {
  return new Date(dateStr).toDateString();
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isInbound = message.role === "user";

  const bubbleClass = cn(
    "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm",
    isInbound
      ? "bg-zinc-800 text-zinc-100 rounded-bl-sm"
      : "bg-indigo-600 text-white rounded-br-sm"
  );

  return (
    <div
      className={cn(
        "flex flex-col gap-0.5",
        isInbound ? "items-start" : "items-end"
      )}
    >
      {!isInbound && (
        <span className="text-[10px] text-zinc-500 px-1">🤖 Bot</span>
      )}

      <div className={bubbleClass}>
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>

      <span className="text-[10px] text-zinc-600 px-1">
        {formatTime(message.created_at)}
      </span>
    </div>
  );
}

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="flex flex-col gap-3">
      {messages.length === 0 && (
        <p className="text-center text-sm text-zinc-600 py-8">
          Nenhuma mensagem ainda
        </p>
      )}
      {messages.map((msg, index) => {
        const currentDay = toDateKey(msg.created_at);
        const prevDay =
          index > 0 ? toDateKey(messages[index - 1].created_at) : null;
        const showSeparator = currentDay !== prevDay;

        return (
          <div key={index} className="flex flex-col gap-3">
            {showSeparator && (
              <div className="flex items-center justify-center my-1">
                <span className="bg-zinc-800 text-zinc-400 text-[11px] font-medium px-3 py-1 rounded-full select-none">
                  {formatDateSeparator(msg.created_at)}
                </span>
              </div>
            )}
            <MessageBubble message={msg} />
          </div>
        );
      })}
    </div>
  );
}
