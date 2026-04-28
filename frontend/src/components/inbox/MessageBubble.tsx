"use client";

import { cn } from "@/lib/utils";

export interface ChatMessage {
  role: string;
  content: string;
  created_at: string;
}

const TZ = "America/Argentina/Buenos_Aires";

function formatTime(dateStr: string) {
  return new Date(dateStr).toLocaleTimeString("pt-BR", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toDateKeyTZ(dateStr: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(dateStr));
}

function formatDateSeparator(dateStr: string) {
  const key = toDateKeyTZ(dateStr);
  const todayKey = toDateKeyTZ(new Date().toISOString());
  const yesterdayKey = toDateKeyTZ(new Date(Date.now() - 86_400_000).toISOString());

  if (key === todayKey) return "Hoje";
  if (key === yesterdayKey) return "Ontem";
  return new Date(dateStr).toLocaleDateString("pt-BR", {
    timeZone: TZ,
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function toDateKey(dateStr: string) {
  return toDateKeyTZ(dateStr);
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
