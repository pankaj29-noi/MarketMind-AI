import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ContentViewportProps {
  children: React.ReactNode;
  /** Stable key for enter animation when module switches */
  moduleKey: string;
  className?: string;
  /** Optional faint inner frame for command-center depth */
  framed?: boolean;
}

/**
 * Main workspace viewport. Enter-only transition to avoid remount/exit bugs.
 * Does not change child lifecycle beyond a single enter animation wrapper.
 */
export function ContentViewport({
  children,
  moduleKey,
  className,
  framed = true,
}: ContentViewportProps) {
  const reduceMotion = useReducedMotion();

  return (
    <div
      className={cn(
        "mm-content-viewport relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden",
        framed && "mm-content-frame",
        className
      )}
    >
      <motion.div
        key={moduleKey}
        className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
        initial={reduceMotion ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
      >
        {children}
      </motion.div>
    </div>
  );
}
