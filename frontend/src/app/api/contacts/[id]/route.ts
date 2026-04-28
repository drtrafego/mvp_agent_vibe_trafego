import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { contacts, deals, activities } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const [contact] = await db.select().from(contacts).where(eq(contacts.id, id));

  if (!contact) {
    return NextResponse.json({ error: "Contacto no encontrado" }, { status: 404 });
  }

  const contactDeals = await db.select().from(deals).where(eq(deals.contactId, id));
  const contactActivities = await db.select().from(activities).where(eq(activities.contactId, id));

  return NextResponse.json({ ...contact, deals: contactDeals, activities: contactActivities });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON invalido" }, { status: 400 });
  }

  const [existing] = await db.select().from(contacts).where(eq(contacts.id, id));

  if (!existing) {
    return NextResponse.json({ error: "Contacto no encontrado" }, { status: 404 });
  }

  const updateData: Record<string, unknown> = { updatedAt: new Date() };
  if (body.name !== undefined) updateData.name = body.name;
  if (body.email !== undefined) updateData.email = body.email;
  if (body.phone !== undefined) updateData.phone = body.phone;
  if (body.company !== undefined) updateData.company = body.company;
  if (body.source !== undefined) updateData.source = body.source;
  if (body.temperature !== undefined) updateData.temperature = body.temperature;
  if (body.score !== undefined) updateData.score = Math.max(0, Math.min(100, body.score));
  if (body.notes !== undefined) updateData.notes = body.notes;
  if (body.stage !== undefined) updateData.stage = body.stage;

  const [result] = await db.update(contacts).set(updateData).where(eq(contacts.id, id)).returning();

  return NextResponse.json(result);
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const [existing] = await db.select().from(contacts).where(eq(contacts.id, id));

  if (!existing) {
    return NextResponse.json({ error: "Contacto no encontrado" }, { status: 404 });
  }

  await db.delete(contacts).where(eq(contacts.id, id));
  return NextResponse.json({ success: true });
}
