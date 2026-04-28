import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { contacts } from "@/db/schema";
import { eq, like, or, desc } from "drizzle-orm";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const search = searchParams.get("search");
  const temperature = searchParams.get("temperature");
  const source = searchParams.get("source");

  let query = db.select().from(contacts);

  if (search) {
    query = query.where(
      or(like(contacts.name, `%${search}%`), like(contacts.email, `%${search}%`), like(contacts.company, `%${search}%`))
    ) as typeof query;
  }
  if (temperature) query = query.where(eq(contacts.temperature, temperature)) as typeof query;
  if (source) query = query.where(eq(contacts.source, source)) as typeof query;

  const results = await query.orderBy(desc(contacts.createdAt));
  return NextResponse.json(results);
}

export async function POST(request: NextRequest) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }

  const { name, email, phone, company, source, temperature, score, notes } = body;

  if (!name) {
    return NextResponse.json({ error: "O nome é obrigatório" }, { status: 400 });
  }

  try {
    const now = new Date();
    const [result] = await db.insert(contacts).values({
      name, email: email || null, phone: phone || null, company: company || null,
      source: source || "outro", temperature: temperature || "cold",
      score: score || 0, notes: notes || null, createdAt: now, updatedAt: now,
    }).returning();

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: `Error al crear contacto: ${error instanceof Error ? error.message : "Unknown"}` },
      { status: 500 }
    );
  }
}
