"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Kanban,
  Settings,
  Briefcase,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/pipeline", label: "Pipeline", icon: Kanban },
  { href: "/contacts", label: "Contatos", icon: Users },
  { href: "/inbox", label: "Inbox", icon: MessageSquare },
  { href: "/deals", label: "Deals", icon: Briefcase },
  { href: "/settings", label: "Configurações", icon: Settings },
];

const STORAGE_KEY = "sidebar_collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved !== null) setCollapsed(saved === "true");
  }, []);

  const toggle = () => {
    setCollapsed((prev) => {
      localStorage.setItem(STORAGE_KEY, String(!prev));
      return !prev;
    });
  };

  if (!mounted) return null;

  return (
    <aside
      className={cn(
        "hidden md:flex md:flex-col bg-[var(--sidebar)] text-[var(--sidebar-foreground)] min-h-screen transition-all duration-200",
        collapsed ? "md:w-14" : "md:w-64"
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex h-16 items-center border-b border-[var(--sidebar-border)] shrink-0",
          collapsed ? "justify-center px-0" : "gap-2 px-6"
        )}
      >
        <Briefcase className="h-6 w-6 shrink-0 text-[var(--sidebar-primary)]" />
        {!collapsed && (
          <span className="text-lg font-bold tracking-tight truncate">Auto-CRM</span>
        )}
      </div>

      {/* Nav */}
      <nav className={cn("flex-1 py-4 space-y-1", collapsed ? "px-1" : "px-3")}>
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center rounded-lg py-2.5 text-sm font-medium transition-colors cursor-pointer",
                collapsed ? "justify-center px-0" : "gap-3 px-3",
                isActive
                  ? "bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-foreground)]"
                  : "text-[var(--sidebar-foreground)]/70 hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]"
              )}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {!collapsed && item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer: toggle + versão */}
      <div
        className={cn(
          "border-t border-[var(--sidebar-border)] py-3",
          collapsed ? "flex justify-center px-1" : "px-4"
        )}
      >
        <button
          onClick={toggle}
          title={collapsed ? "Expandir menu" : "Recolher menu"}
          className="flex items-center gap-2 rounded-lg p-2 text-[var(--sidebar-foreground)]/50 hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)] transition-colors cursor-pointer w-full"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4 shrink-0" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4 shrink-0" />
              <span className="text-xs">Recolher</span>
            </>
          )}
        </button>
        {!collapsed && (
          <p className="text-xs text-[var(--sidebar-foreground)]/50 mt-2">
            Powered by Claude
          </p>
        )}
      </div>
    </aside>
  );
}
