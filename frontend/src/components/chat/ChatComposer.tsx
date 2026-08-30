import { ArrowUp, Check, Loader2 } from "lucide-react";
import { useState, useRef, useEffect, useCallback } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  onSubmit?: (v: string) => void;
  disabled?: boolean;
  model?: string;
}

type AnalyzeVisualState = "idle" | "loading" | "success";

export function ChatComposer({ onSubmit, disabled, model }: ChatComposerProps) {
  const [v, setV] = useState("");
  const [focused, setFocused] = useState(false);
  const [btnState, setBtnState] = useState<AnalyzeVisualState>("idle");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prevDisabled = useRef(!!disabled);
  const reduceMotion = useReducedMotion();

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, []);

  useEffect(() => {
    resize();
  }, [v, resize]);

  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  // Reflect real analyzing transitions only — temporary success flash
  useEffect(() => {
    const was = prevDisabled.current;
    prevDisabled.current = !!disabled;
    if (disabled) {
      setBtnState("loading");
      return;
    }
    if (was && !disabled) {
      setBtnState("success");
      const t = window.setTimeout(() => setBtnState("idle"), 1400);
      return () => window.clearTimeout(t);
    }
    setBtnState("idle");
  }, [disabled]);

  // New question entry clears success confirmation
  useEffect(() => {
    if (v.trim() && btnState === "success") setBtnState("idle");
  }, [v, btnState]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = v.trim();
    if (!trimmed || disabled) return;
    onSubmit?.(trimmed);
    setV("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const activated = focused && !disabled;
  const phaseLabel = disabled
    ? "ANALYSIS RUNNING"
    : activated
      ? "SYSTEM ACTIVE"
      : "AWAITING INPUT";

  return (
    <form onSubmit={handleSubmit} className="relative mm-phase-ready-accent mm-phase-running-accent">
      <motion.div
        animate={
          reduceMotion
            ? undefined
            : {
                boxShadow: activated
                  ? "0 0 0 1px color-mix(in oklch, var(--primary) 45%, transparent), 0 0 28px -8px color-mix(in oklch, var(--primary) 35%, transparent)"
                  : disabled
                    ? "0 0 0 1px color-mix(in oklch, var(--primary) 30%, transparent)"
                    : "0 0 0 1px color-mix(in oklch, var(--border) 100%, transparent), 0 0 0 transparent",
              }
        }
        transition={{ duration: 0.22 }}
        className={cn(
          "surface-command relative overflow-hidden",
          (activated || disabled) && "border-primary/40"
        )}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-3 py-1.5">
          <div className="flex items-center gap-2">
            <span className="type-mono text-[10px] text-primary/80">QUERY</span>
            <span className="text-border">//</span>
            <span className="type-meta">{phaseLabel}</span>
          </div>
          <div className="flex items-center gap-2">
            {model && (
              <span className="hidden type-mono text-[10px] text-muted-foreground sm:inline">
                {model}
              </span>
            )}
            <kbd className="type-mono hidden rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">
              ↵ Enter
            </kbd>
          </div>
        </div>

        <div className="flex items-end gap-2 px-3 py-2.5">
          <span
            className={cn(
              "mb-2 select-none font-mono text-sm transition-colors duration-[var(--duration-fast)]",
              activated || disabled ? "text-primary" : "text-muted-foreground/60"
            )}
            aria-hidden
          >
            ›
          </span>
          <textarea
            ref={textareaRef}
            value={v}
            onChange={(e) => setV(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            rows={1}
            placeholder="Ask about buyers, suppliers, products, leads, or orders…"
            className="scrollbar-thin max-h-40 min-h-[36px] flex-1 resize-none border-0 bg-transparent py-2 font-mono text-[13px] leading-relaxed text-foreground placeholder:font-sans placeholder:text-muted-foreground focus:outline-none focus-visible:outline-none"
            disabled={disabled}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e as unknown as React.FormEvent);
              }
            }}
          />
          <button
            type="submit"
            disabled={disabled || (!v.trim() && btnState !== "success")}
            data-state={btnState}
            className={cn(
              "mm-analyze-btn mb-1 inline-flex h-9 items-center gap-1.5 px-3 text-[11px] font-semibold uppercase tracking-[0.08em]",
              "bg-primary text-primary-foreground",
              "hover:bg-primary/90",
              "disabled:cursor-not-allowed",
              btnState === "success" ? "opacity-100" : "disabled:opacity-40",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            )}
            aria-label="Analyze"
          >
            {btnState === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : btnState === "success" ? (
              <>
                <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                <span className="hidden sm:inline">Done</span>
              </>
            ) : (
              <>
                <span className="hidden sm:inline">Analyze</span>
                <ArrowUp className="h-3.5 w-3.5 transition-transform group-hover:-translate-y-0.5" />
              </>
            )}
          </button>
        </div>
      </motion.div>
    </form>
  );
}
