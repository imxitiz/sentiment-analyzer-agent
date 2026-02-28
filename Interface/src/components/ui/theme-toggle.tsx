/**
 * ThemeToggle — cycles between dark / light / system themes.
 *
 * Shows a sun/moon/monitor icon based on current theme.
 */

import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "@/hooks/use-theme";
import type { Theme } from "@/hooks/use-theme";
import { cn } from "@/lib/utils";

const CYCLE: Theme[] = ["dark", "light", "system"];
const ICONS: Record<Theme, typeof Sun> = {
  dark: Moon,
  light: Sun,
  system: Monitor,
};
const LABELS: Record<Theme, string> = {
  dark: "Dark mode",
  light: "Light mode",
  system: "System theme",
};

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, setTheme } = useTheme();
  const Icon = ICONS[theme];

  const next = () => {
    const idx = CYCLE.indexOf(theme);
    setTheme(CYCLE[(idx + 1) % CYCLE.length]!);
  };

  if (collapsed) {
    return (
      <button
        onClick={next}
        className="p-2 rounded-lg hover:bg-accent transition-colors"
        title={LABELS[theme]}
      >
        <Icon className="h-4 w-4" />
      </button>
    );
  }

  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted p-0.5">
      {CYCLE.map((t) => {
        const I = ICONS[t];
        return (
          <button
            key={t}
            onClick={() => setTheme(t)}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors",
              theme === t
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
            title={LABELS[t]}
          >
            <I className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{t === "system" ? "Auto" : t.charAt(0).toUpperCase() + t.slice(1)}</span>
          </button>
        );
      })}
    </div>
  );
}
