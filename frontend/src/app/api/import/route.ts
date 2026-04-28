import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { contacts } from "@/db/schema";

export async function POST(request: NextRequest) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const { contacts: contactList } = body;
  if (!Array.isArray(contactList) || contactList.length === 0) {
    return NextResponse.json({ error: "Um array de contatos é obrigatório" }, { status: 400 });
  }

  const results = { imported: 0, failed: 0, errors: [] as string[] };
  const now = new Date();

  for (const contact of contactList) {
    if (!contact.name) {
      results.failed++;
      results.errors.push(`Contacto sin nombre: ${JSON.stringify(contact)}`);
      continue;
    }
    try {
      await db.insert(contacts).values({
        name: contact.name, email: contact.email || null, phone: contact.phone || null,
        company: contact.company || null, source: contact.source || "import",
        temperature: contact.temperature || "cold", score: contact.score || 0,
        notes: contact.notes || null, createdAt: now, updatedAt: now,
      });
      results.imported++;
    } catch (error) {
      results.failed++;
      results.errors.push(`Error importando ${contact.name}: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  return NextResponse.json(results, { status: results.failed > 0 ? 207 : 201 });
}
