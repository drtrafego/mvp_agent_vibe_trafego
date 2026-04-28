import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { activities, contacts } from "@/db/schema";
import { eq, desc } from "drizzle-orm";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const contactId = searchParams.get("contactId");
  const dealId = searchParams.get("dealId");

  let query = db.select({
    id: activities.id, type: activities.type, description: activities.description,
    contactId: activities.contactId, dealId: activities.dealId,
    scheduledAt: activities.scheduledAt, completedAt: activities.completedAt,
    createdAt: activities.createdAt, contactName: contacts.name,
  }).from(activities).leftJoin(contacts, eq(activities.contactId, contacts.id));

  if (contactId) query = query.where(eq(activities.contactId, contactId)) as typeof query;
  if (dealId) query = query.where(eq(activities.dealId, dealId)) as typeof query;

  const results = await query.orderBy(desc(activities.createdAt));
  return NextResponse.json(results);
}

export async function POST(request: NextRequest) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const { type, description, contactId, dealId, scheduledAt } = body;
  if (!type || !description || !contactId) {
    return NextResponse.json({ error: "Tipo, descrição e contato são obrigatórios" }, { status: 400 });
  }

  try {
    const [result] = await db.insert(activities).values({
      type, description, contactId, dealId: dealId || null,
      scheduledAt: scheduledAt ? new Date(scheduledAt) : null,
      completedAt: null, createdAt: new Date(),
    }).returning();

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: `Erro ao criar atividade: ${error instanceof Error ? error.message : "Unknown"}` },
      { status: 500 }
    );
  }
}
