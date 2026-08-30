import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function ReportCard({
  children,
  className,
  eyebrow,
  title,
  action,
}: {
  children: ReactNode;
  className?: string;
  eyebrow?: string;
  title?: string;
  action?: ReactNode;
}) {
  return (
    <section className={cn("surface-primary p-5 sm:p-6 border border-border/70 transition-colors duration-[var(--duration-normal)]", className)}>
      {(eyebrow || title || action) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {eyebrow && (
              <div className="type-section-label text-primary">{eyebrow}</div>
            )}
            {title && <h3 className="mt-1 truncate text-base font-semibold tracking-tight sm:text-lg">{title}</h3>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      {children}
    </section>
  );
}