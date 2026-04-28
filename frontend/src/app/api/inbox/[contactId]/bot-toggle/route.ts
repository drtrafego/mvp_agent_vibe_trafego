import { NextResponse } from "next/server";
import { db } from "@/db";
import { contacts } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function PATCH(
  _req: Request,
  { params }: { params: Promise<{ contactId: string }> }
) {
  const { contactId } = await params;

  const [contact] = await db.select({ id: contacts.id, botActive: contacts.botActive }).from(contacts).where(eq(contacts.id, contactId));
  if (!contact) {
    return NextResponse.json({ error: "Contato não encontrado" }, { status: 404 });
  }

  const newValue = !contact.botActive;

  await db.update(contacts)
    .set({ botActive: newValue, updatedAt: new Date() })
    .where(eq(contacts.id, contactId));

  return NextResponse.json({ botActive: newValue });
}
