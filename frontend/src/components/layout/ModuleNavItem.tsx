import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface ModuleNavItemProps {
  label: string;
  icon: React.ReactNode;
  active: boolean;
  onClick: () => void;
  collapsed?: boolean;
}

export function ModuleNavItem({
  label,
  icon,
  active,
  onClick,
}: ModuleNavItemProps) {
  const reduceMotion = useReducedMotion();

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex w-full items-center gap-2.5 overflow-hidden px-2.5 py-2 text-left transition-colors duration-[var(--duration-fast)]",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50",
        active
          ? "text-foreground"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      {active && (
        <motion.span
          layoutId={reduceMotion ? undefined : "mm-module-active-rail"}
          className="absolute inset-y-1 left-0 w-[2px] rounded-full bg-primary"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}

      <span
        className={cn(
          "absolute inset-0 rounded-md transition-opacity duration-[var(--duration-normal)]",
          active
            ? "bg-primary/[0.07] opacity-100"
            : "bg-sidebar-accent/0 opacity-0 group-hover:bg-sidebar-accent/55 group-hover:opacity-100"
        )}
      />

      <span
        className={cn(
          "relative z-[1] grid h-6 w-6 shrink-0 place-items-center transition-transform duration-[var(--duration-normal)] group-hover:translate-x-0.5",
          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        )}
      >
        {icon}
      </span>

      <span
        className={cn(
          "type-section-label relative z-[1] flex-1 transition-transform duration-[var(--duration-normal)] group-hover:translate-x-0.5",
          active ? "text-foreground" : ""
        )}
      >
        {label}
      </span>

      {active && (
        <motion.span
          className="relative z-[1] h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
          animate={reduceMotion ? undefined : { opacity: [0.45, 1, 0.45] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </button>
  );
}
