"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Link2, Wallet } from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/matches", label: "Splitwise Matches", icon: Link2 },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-border bg-surface px-4 py-6 sm:flex">
      <div className="mb-8 flex items-center gap-2.5 px-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white">
          <Wallet size={16} strokeWidth={2.2} />
        </span>
        <div>
          <p className="text-sm font-semibold leading-tight">Expenses</p>
          <p className="text-xs text-muted">Statement Analyzer</p>
        </div>
      </div>

      <nav aria-label="Main navigation" className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-accent-faint font-medium text-accent-deep"
                  : "text-muted hover:bg-background hover:text-foreground"
              }`}
            >
              <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
