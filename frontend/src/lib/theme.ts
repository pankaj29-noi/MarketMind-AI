export const THEME_STORAGE_KEY = 'marketmind-theme';

export type ThemeMode = 'light' | 'dark';

export function readStoredTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* private mode / blocked storage */
  }
  return 'dark';
}

export function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement;
  const isDark = mode === 'dark';
  root.classList.toggle('dark', isDark);
  root.style.colorScheme = mode;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* private mode / blocked storage */
  }
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) meta.setAttribute('content', mode);
}

export function getChartThemeColors(): {
  font: string;
  grid: string;
  line: string;
} {
  const styles = getComputedStyle(document.documentElement);
  return {
    font: styles.getPropertyValue('--chart-label').trim() || '#18181b',
    grid: styles.getPropertyValue('--chart-grid').trim() || 'rgba(24, 24, 27, 0.1)',
    line: styles.getPropertyValue('--chart-axis').trim() || 'rgba(24, 24, 27, 0.16)',
  };
}
