"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  DndContext,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { toast } from "sonner";
import type { Temperature } from "@/types";

function relativeDays(ts: number | null): string | null {
  if (!ts) return null;
  const diff = Math.floor((Date.now() - ts) / (1000 * 60 * 60 * 24));
  if (diff === 0) return "hoje";
  if (diff === 1) return "ontem";
  return `${diff}d atrás`;
}

interface Lead {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  nicho: string | null;
  temperature: string;
  score: number;
  followupCount: number;
  lastLeadMsgAt: number | null;
}

interface Column {
  id: string;
  label: string;
  color: string;
  contacts: Lead[];
}

function LeadCard({ lead, isDragging }: { lead: Lead; isDragging?: boolean }) {
  const router = useRouter();
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: lead.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Card
        className="p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow select-none"
        onClick={() => router.push(`/contacts/${lead.id}`)}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium leading-tight truncate">{lead.name}</p>
          <StatusBadge temperature={lead.temperature as Temperature} />
        </div>
        {lead.nicho && (
          <p className="text-xs text-primary/70 font-medium mt-1 truncate">{lead.nicho}</p>
        )}
        {lead.email && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{lead.email}</p>
        )}
        {lead.phone && (
          <p className="text-xs text-muted-foreground truncate">{lead.phone}</p>
        )}
        <div className="mt-2 flex items-center gap-1">
          <div className="h-1 flex-1 rounded bg-muted overflow-hidden">
            <div
              className="h-full rounded bg-primary transition-all"
              style={{ width: `${lead.score}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-8 text-right">{lead.score}</span>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
          {lead.followupCount > 0 && (
            <span className="bg-muted rounded px-1.5 py-0.5">FU: {lead.followupCount}/6</span>
          )}
          {relativeDays(lead.lastLeadMsgAt) && (
            <span className="ml-auto">{relativeDays(lead.lastLeadMsgAt)}</span>
          )}
        </div>
      </Card>
    </div>
  );
}

function DroppableColumn({ column }: { column: Column }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });

  return (
    <div className="flex-none w-64">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: column.color }} />
        <span className="font-semibold text-sm">{column.label}</span>
        <Badge variant="secondary" className="ml-auto text-xs">
          {column.contacts.length}
        </Badge>
      </div>
      <SortableContext items={column.contacts.map((c) => c.id)} strategy={verticalListSortingStrategy}>
        <div
          ref={setNodeRef}
          className={`space-y-2 min-h-[200px] rounded-lg p-2 transition-colors ${isOver ? "bg-muted/50" : ""}`}
        >
          {column.contacts.map((lead) => (
            <LeadCard key={lead.id} lead={lead} />
          ))}
          {column.contacts.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-8">Vazio</p>
          )}
        </div>
      </SortableContext>
    </div>
  );
}

interface LeadPipelineBoardProps {
  initialColumns: Column[];
}

export function LeadPipelineBoard({ initialColumns }: LeadPipelineBoardProps) {
  const [columns, setColumns] = useState(initialColumns);
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const activeLead = activeId
    ? columns.flatMap((c) => c.contacts).find((l) => l.id === activeId)
    : null;

  const findColumnOfLead = useCallback((leadId: string) => {
    return columns.find((col) => col.contacts.some((c) => c.id === leadId));
  }, [columns]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  }, []);

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) return;

    const activeCol = findColumnOfLead(active.id as string);
    if (!activeCol) return;

    const overColId = columns.find((c) => c.id === over.id)?.id
      ?? findColumnOfLead(over.id as string)?.id;

    if (!overColId || overColId === activeCol.id) return;

    setColumns((cols) => {
      const lead = activeCol.contacts.find((c) => c.id === active.id)!;
      return cols.map((col) => {
        if (col.id === activeCol.id) return { ...col, contacts: col.contacts.filter((c) => c.id !== active.id) };
        if (col.id === overColId) return { ...col, contacts: [...col.contacts, lead] };
        return col;
      });
    });
  }, [columns, findColumnOfLead]);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;

    const newCol = columns.find((c) => c.id === over.id)
      ?? columns.find((c) => c.contacts.some((l) => l.id === over.id));

    if (!newCol) return;

    try {
      await fetch(`/api/contacts/${active.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: newCol.id }),
      });
    } catch {
      toast.error("Erro ao mover lead");
    }
  }, [columns]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-3 overflow-x-auto pb-4">
        {columns.map((col) => (
          <DroppableColumn key={col.id} column={col} />
        ))}
      </div>
      <DragOverlay>
        {activeLead && (
          <Card className="p-3 shadow-xl w-64 rotate-2 cursor-grabbing opacity-90">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium truncate">{activeLead.name}</p>
              <StatusBadge temperature={activeLead.temperature as Temperature} />
            </div>
            {activeLead.nicho && (
              <p className="text-xs text-primary/70 font-medium mt-1 truncate">{activeLead.nicho}</p>
            )}
            {activeLead.email && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{activeLead.email}</p>
            )}
          </Card>
        )}
      </DragOverlay>
    </DndContext>
  );
}
