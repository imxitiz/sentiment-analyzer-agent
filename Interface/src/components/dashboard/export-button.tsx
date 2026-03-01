/**
 * ExportButton — dropdown button to export analysis results.
 *
 * Supports JSON, CSV, and Markdown formats. Downloads are triggered
 * via direct URL navigation (no client-side file generation needed).
 */

import { useState } from "react";
import { Download, FileJson, FileSpreadsheet, FileText } from "lucide-react";
import { api } from "@/lib/api";
import type { ExportFormat } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ExportButtonProps {
  sessionId: string;
  version?: number;
  disabled?: boolean;
}

const FORMATS: { value: ExportFormat; label: string; icon: typeof Download; desc: string }[] = [
  { value: "json", label: "JSON", icon: FileJson, desc: "Full structured data" },
  { value: "csv", label: "CSV", icon: FileSpreadsheet, desc: "Spreadsheet-ready posts" },
  { value: "md", label: "Markdown", icon: FileText, desc: "Formatted report" },
];

export function ExportButton({ sessionId, version, disabled }: ExportButtonProps) {
  const [open, setOpen] = useState(false);

  const handleExport = (format: ExportFormat) => {
    const url = api.sessions.exportUrl(sessionId, format, version);
    window.open(url, "_blank");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium",
          "border border-border text-muted-foreground",
          "hover:bg-accent hover:text-accent-foreground transition-colors",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        title="Export analysis results"
      >
        <Download className="h-3.5 w-3.5" />
        Export
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          {/* Dropdown */}
          <div
            className={cn(
              "absolute right-0 top-full mt-1 z-50 w-56",
              "rounded-lg border border-border bg-popover shadow-lg",
              "animate-in fade-in-0 zoom-in-95",
            )}
          >
            <div className="p-1">
              <p className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                Export Format
              </p>
              {FORMATS.map(({ value, label, icon: Icon, desc }) => (
                <button
                  key={value}
                  onClick={() => handleExport(value)}
                  className={cn(
                    "w-full flex items-center gap-3 px-2 py-2 rounded-md text-sm",
                    "hover:bg-accent hover:text-accent-foreground transition-colors",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="text-left">
                    <div className="font-medium">{label}</div>
                    <div className="text-xs text-muted-foreground">{desc}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
