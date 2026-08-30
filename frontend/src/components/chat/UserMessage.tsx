import { User } from "lucide-react";

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-2xl items-start gap-3">
        <div className="border border-primary/25 bg-primary/[0.07] px-4 py-3">
          <div className="type-section-label mb-1.5 text-[10px] text-primary/70">Query</div>
          <p className="text-sm leading-relaxed text-foreground">{text}</p>
        </div>
        <div className="grid h-8 w-8 shrink-0 place-items-center border border-border bg-secondary">
          <User className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
    </div>
  );
}
