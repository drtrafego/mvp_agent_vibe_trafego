import type { Temperature, LeadSource, ActivityType } from "@/types";

export const TEMPERATURE_CONFIG: Record<
  Temperature,
  { label: string; color: string; bgColor: string }
> = {
  cold: { label: "Frio", color: "#64748b", bgColor: "#f1f5f9" },
  warm: { label: "Morno", color: "#ea580c", bgColor: "#fff7ed" },
  hot: { label: "Quente", color: "#dc2626", bgColor: "#fef2f2" },
};

export const SOURCE_LABELS: Record<LeadSource, string> = {
  website: "Site",
  whatsapp: "WhatsApp",
  referido: "Indicação",
  redes_sociais: "Redes sociais",
  ligacao_fria: "Ligação fria",
  email: "Email",
  formulario: "Formulário",
  evento: "Evento",
  import: "Importado",
  webhook: "Webhook",
  outro: "Outro",
};

export const ACTIVITY_TYPE_CONFIG: Record<
  ActivityType,
  { label: string; icon: string }
> = {
  call: { label: "Ligação", icon: "Phone" },
  email: { label: "Email", icon: "Mail" },
  meeting: { label: "Reunião", icon: "Users" },
  note: { label: "Nota", icon: "FileText" },
  follow_up: { label: "Acompanhamento", icon: "Clock" },
};

export function formatCurrency(cents: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);
}

export function cleanPhoneForWhatsApp(phone: string): string {
  // "+55 11 91234-5678" → "5511912345678"
  return phone.replace(/[\s\-\(\)]/g, "").replace(/^\+/, "");
}

function toDate(date: Date | number): Date {
  if (date instanceof Date) return date;
  // If number is less than 1e12, it's in seconds; otherwise milliseconds
  return new Date(date < 1e12 ? date * 1000 : date);
}

export function formatDate(date: Date | number | null): string {
  if (!date) return "-";
  const d = toDate(date);
  return new Intl.DateTimeFormat("pt-BR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(d);
}

export function formatRelativeDate(date: Date | number): string {
  const d = toDate(date);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Hoje";
  if (diffDays === 1) return "Ontem";
  if (diffDays < 7) return `Há ${diffDays} dias`;
  if (diffDays < 30) return `Há ${Math.floor(diffDays / 7)} semanas`;
  return formatDate(date);
}
