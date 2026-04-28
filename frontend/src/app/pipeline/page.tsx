import { db } from "@/db";
import { contacts } from "@/db/schema";
import { asc } from "drizzle-orm";
import { LeadPipelineBoard } from "@/components/pipeline/LeadPipelineBoard";

export const dynamic = "force-dynamic";

const STAGES = [
  { id: "novo", label: "Novo", color: "#64748b" },
  { id: "qualificando", label: "Qualificando", color: "#3b82f6" },
  { id: "interesse", label: "Interesse", color: "#f59e0b" },
  { id: "agendado", label: "Agendado", color: "#8b5cf6" },
  { id: "realizada", label: "Realizada", color: "#10b981" },
  { id: "sem_interesse", label: "Sem interesse", color: "#ef4444" },
  { id: "perdido", label: "Perdido", color: "#dc2626" },
  { id: "bloqueado", label: "Bloqueado", color: "#1f2937" },
];

export default async function PipelinePage() {
  const allContacts = await db.select().from(contacts).orderBy(asc(contacts.createdAt));

  const columns = STAGES.map((stage) => ({
    ...stage,
    contacts: allContacts
      .filter((c) => (c.stage || "novo") === stage.id)
      .map((c) => ({
        id: c.id,
        name: c.name,
        phone: c.phone,
        email: c.email,
        nicho: c.nicho,
        temperature: c.temperature,
        score: c.score,
        followupCount: c.followupCount ?? 0,
        lastLeadMsgAt: c.lastLeadMsgAt ? c.lastLeadMsgAt.getTime() : null,
      })),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pipeline de Leads</h1>
        <p className="text-muted-foreground">Leads organizados por etapa. O bot move automaticamente conforme a conversa evolui.</p>
      </div>
      <LeadPipelineBoard initialColumns={columns} />
    </div>
  );
}
