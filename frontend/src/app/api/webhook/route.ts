import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { contacts, activities, crmSettings } from "@/db/schema";
import { eq } from "drizzle-orm";

const FIELD_MAP: Record<string, string> = {
  name: "name", nombre: "name", full_name: "name", fullname: "name",
  first_name: "name", nombre_completo: "name",
  email: "email", correo: "email", email_address: "email", correo_electronico: "email",
  phone: "phone", telefono: "phone", phone_number: "phone", cel: "phone",
  celular: "phone", whatsapp: "phone", movil: "phone",
  company: "company", empresa: "company", company_name: "company",
  negocio: "company", organizacion: "company",
  notes: "notes", notas: "notes", message: "notes", mensaje: "notes",
  comments: "notes", comentarios: "notes", descripcion: "notes",
};

function extractFields(payload: Record<string, unknown>): Record<string, string> {
  const data = payload.data && typeof payload.data === "object" ? (payload.data as Record<string, unknown>) : payload;
  const result: Record<string, string> = {};

  for (const [key, value] of Object.entries(data)) {
    if (typeof value !== "string" && typeof value !== "number") continue;
    const normalizedKey = key.toLowerCase().trim().replace(/\s+/g, "_");
    const mappedField = FIELD_MAP[normalizedKey];
    if (mappedField && !result[mappedField]) result[mappedField] = String(value).trim();
  }

  if (!result.name) {
    const firstName = data.first_name || data.nombre || data.firstName || data.primer_nombre;
    const lastName = data.last_name || data.apellido || data.lastName || data.apellidos;
    if (firstName) result.name = [firstName, lastName].filter(Boolean).join(" ").trim();
  }

  return result;
}

export async function POST(request: NextRequest) {
  const [stored] = await db.select().from(crmSettings).where(eq(crmSettings.key, "webhook_secret"));

  if (stored) {
    const secretHeader = request.headers.get("x-webhook-secret");
    if (!secretHeader || secretHeader !== stored.value) {
      return NextResponse.json({ error: "Secret inválido ou faltante" }, { status: 401 });
    }
  }

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON invalido" }, { status: 400 });
  }

  const fields = extractFields(payload);

  if (!fields.name) {
    return NextResponse.json({
      error: "Campo 'name' ou 'nome' é obrigatório",
      received: Object.keys(payload),
      hint: "Campos suportados: name, nome, full_name, email, correo, phone, telefone, company, empresa, notes, notas, message",
    }, { status: 400 });
  }

  try {
    const now = new Date();
    const [contact] = await db.insert(contacts).values({
      name: fields.name, email: fields.email || null, phone: fields.phone || null,
      company: fields.company || null, source: "webhook", temperature: "cold",
      score: 0, notes: fields.notes || null, createdAt: now, updatedAt: now,
    }).returning();

    await db.insert(activities).values({
      type: "note",
      description: `Lead recebido via webhook${fields.company ? ` (${fields.company})` : ""}`,
      contactId: contact.id, createdAt: now,
    });

    return NextResponse.json({ success: true, contact: { id: contact.id, name: contact.name, email: contact.email, source: contact.source } }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: `Erro ao criar contato: ${error instanceof Error ? error.message : "Unknown"}` }, { status: 500 });
  }
}
