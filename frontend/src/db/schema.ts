import { pgSchema, text, integer, boolean, timestamp } from "drizzle-orm/pg-core";

const agente_vibe = pgSchema("agente_vibe");

export const contacts = agente_vibe.table("contacts", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  name: text("name").notNull(),
  email: text("email"),
  phone: text("phone"),
  company: text("company"),
  source: text("source").notNull().default("outro"),
  temperature: text("temperature").notNull().default("cold"),
  score: integer("score").notNull().default(0),
  notes: text("notes"),
  nicho: text("nicho"),
  stage: text("stage"),
  followupCount: integer("followup_count").default(0),
  lastLeadMsgAt: timestamp("last_lead_msg_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

export const pipelineStages = agente_vibe.table("pipeline_stages", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  name: text("name").notNull(),
  order: integer("order").notNull(),
  color: text("color").notNull().default("#64748b"),
  isWon: boolean("is_won").notNull().default(false),
  isLost: boolean("is_lost").notNull().default(false),
});

export const deals = agente_vibe.table("deals", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  title: text("title").notNull(),
  value: integer("value").notNull().default(0),
  stageId: text("stage_id")
    .notNull()
    .references(() => pipelineStages.id),
  contactId: text("contact_id")
    .notNull()
    .references(() => contacts.id),
  expectedClose: timestamp("expected_close"),
  probability: integer("probability").notNull().default(0),
  notes: text("notes"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

export const activities = agente_vibe.table("activities", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  type: text("type").notNull(),
  description: text("description").notNull(),
  contactId: text("contact_id")
    .notNull()
    .references(() => contacts.id),
  dealId: text("deal_id").references(() => deals.id),
  scheduledAt: timestamp("scheduled_at"),
  completedAt: timestamp("completed_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const crmSettings = agente_vibe.table("crm_settings", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
});
