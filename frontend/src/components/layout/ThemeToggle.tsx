import { Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ThemeToggleProps {
  isDark: boolean;
  onToggle: () => void;
  className?: string;
}

export function ThemeToggle({ isDark, onToggle, className }: ThemeToggleProps) {
  return (
    <div
      className={cn(
        'inline-flex items-center rounded-lg border border-border bg-muted/60 p-0.5',
        className
      )}
      role="group"
      aria-label="Color theme"
    >
      <button
        type="button"
        onClick={() => {
          if (isDark) onToggle();
        }}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-colors',
          !isDark
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        )}
        aria-pressed={!isDark}
        aria-label="Light mode"
        title="Light mode"
      >
        <Sun className="h-3.5 w-3.5" aria-hidden />
        <span>Light</span>
      </button>
      <button
        type="button"
        onClick={() => {
          if (!isDark) onToggle();
        }}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-colors',
          isDark
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        )}
        aria-pressed={isDark}
        aria-label="Dark mode"
        title="Dark mode"
      >
        <Moon className="h-3.5 w-3.5" aria-hidden />
        <span>Dark</span>
      </button>
    </div>
  );
}
