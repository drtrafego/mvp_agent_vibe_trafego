import { db } from "@/db";
import { contacts, deals, activities, pipelineStages } from "@/db/schema";
import { eq, desc } from "drizzle-orm";
import { notFound } from "next/navigation";
import { ContactDetailClient } from "@/components/contacts/ContactDetail";

export const dynamic = "force-dynamic";

export default async function ContactDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [raw] = await db.select().from(contacts).where(eq(contacts.id, id));
  if (!raw) notFound();

  const base = raw.temperature === "hot" ? 50 : raw.temperature === "warm" ? 30 : 10;
  const bonus = (raw.email ? 10 : 0) + (raw.phone ? 10 : 0) + (raw.company ? 5 : 0);
  const contact = { ...raw, score: raw.score !== 0 ? raw.score : Math.min(100, base + bonus) };

  const contactDeals = await db.select({
    id: deals.id, title: deals.title, value: deals.value,
    stageId: deals.stageId, probability: deals.probability,
    createdAt: deals.createdAt, stageName: pipelineStages.name, stageColor: pipelineStages.color,
  }).from(deals).leftJoin(pipelineStages, eq(deals.stageId, pipelineStages.id)).where(eq(deals.contactId, id));

  const contactActivities = await db.select().from(activities).where(eq(activities.contactId, id)).orderBy(desc(activities.createdAt));

  return (
    <ContactDetailClient
      contact={contact as Parameters<typeof ContactDetailClient>[0]["contact"]}
      deals={contactDeals as Parameters<typeof ContactDetailClient>[0]["deals"]}
      activities={contactActivities as Parameters<typeof ContactDetailClient>[0]["activities"]}
    />
  );
}
