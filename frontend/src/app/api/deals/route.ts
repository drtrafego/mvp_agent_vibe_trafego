import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { deals, contacts, pipelineStages } from "@/db/schema";
import { eq, desc, asc } from "drizzle-orm";

export async function GET() {
  const results = await db.select({
    id: deals.id, title: deals.title, value: deals.value,
    stageId: deals.stageId, contactId: deals.contactId,
    expectedClose: deals.expectedClose, probability: deals.probability,
    notes: deals.notes, createdAt: deals.createdAt, updatedAt: deals.updatedAt,
    contactName: contacts.name, contactEmail: contacts.email,
    contactTemperature: contacts.temperature, stageName: pipelineStages.name,
    stageColor: pipelineStages.color, stageOrder: pipelineStages.order,
    stageIsWon: pipelineStages.isWon, stageIsLost: pipelineStages.isLost,
  }).from(deals)
    .leftJoin(contacts, eq(deals.contactId, contacts.id))
    .leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id))
    .orderBy(desc(deals.createdAt));

  return NextResponse.json(results);
}

export async function POST(request: NextRequest) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const { title, value, stageId, contactId, expectedClose, probability, notes } = body;

  if (!title || !contactId) {
    return NextResponse.json({ error: "Título e contato são obrigatórios" }, { status: 400 });
  }

  let finalStageId = stageId;
  if (!finalStageId) {
    const [firstStage] = await db.select().from(pipelineStages).orderBy(asc(pipelineStages.order)).limit(1);
    finalStageId = firstStage?.id;
  }

  if (!finalStageId) {
    return NextResponse.json({ error: "Nenhuma etapa de pipeline configurada" }, { status: 400 });
  }

  try {
    const now = new Date();
    const [result] = await db.insert(deals).values({
      title, value: value || 0, stageId: finalStageId, contactId,
      expectedClose: expectedClose ? new Date(expectedClose) : null,
      probability: Math.max(0, Math.min(100, Number(probability) || 0)),
      notes: notes || null, createdAt: now, updatedAt: now,
    }).returning();

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Unknown";
    if (msg.includes("FOREIGN KEY") || msg.includes("foreign key")) {
      return NextResponse.json({ error: "Contacto no encontrado" }, { status: 400 });
    }
    return NextResponse.json({ error: `Error al crear deal: ${msg}` }, { status: 500 });
  }
}
