import { NextRequest } from "next/server";
import { db } from "@/db";
import { contacts, deals, pipelineStages } from "@/db/schema";
import { eq, desc, asc } from "drizzle-orm";
import { formatDate, formatCurrency, SOURCE_LABELS } from "@/lib/constants";
import type { LeadSource } from "@/types";

function escapeCSV(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  const str = String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildCSV(headers: string[], rows: string[][]): string {
  return [headers.map(escapeCSV).join(","), ...rows.map((r) => r.map(escapeCSV).join(","))].join("\n");
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const type = searchParams.get("type") || "contacts";
  const today = new Date().toISOString().split("T")[0];

  if (type === "contacts") {
    const allContacts = await db.select().from(contacts).orderBy(desc(contacts.createdAt));
    const headers = ["Nome", "Email", "Telefone", "Empresa", "Origem", "Temperatura", "Score", "Notas", "Data de criação"];
    const rows = allContacts.map((c) => [
      c.name, c.email || "", c.phone || "", c.company || "",
      SOURCE_LABELS[c.source as LeadSource] || c.source,
      c.temperature === "hot" ? "Quente" : c.temperature === "warm" ? "Morno" : "Frio",
      String(c.score), c.notes || "", formatDate(c.createdAt),
    ]);
    return new Response("\ufeff" + buildCSV(headers, rows), {
      headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": `attachment; filename="contatos-${today}.csv"` },
    });
  }

  if (type === "deals") {
    const allDeals = await db.select({
      title: deals.title, value: deals.value, probability: deals.probability,
      notes: deals.notes, expectedClose: deals.expectedClose, createdAt: deals.createdAt,
      contactName: contacts.name, stageName: pipelineStages.name,
    }).from(deals)
      .leftJoin(contacts, eq(deals.contactId, contacts.id))
      .leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id))
      .orderBy(asc(pipelineStages.order));

    const headers = ["Título", "Valor", "Contato", "Etapa", "Probabilidade", "Fechamento Estimado", "Notas", "Data de criação"];
    const rows = allDeals.map((d) => [
      d.title, formatCurrency(d.value), d.contactName || "", d.stageName || "",
      `${d.probability}%`, formatDate(d.expectedClose), d.notes || "", formatDate(d.createdAt),
    ]);
    return new Response("\ufeff" + buildCSV(headers, rows), {
      headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": `attachment; filename="deals-${today}.csv"` },
    });
  }

  return new Response("Tipo inválido. Use ?type=contacts ou ?type=deals", { status: 400 });
}
