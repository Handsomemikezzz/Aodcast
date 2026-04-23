import { useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";
import { cn } from "../lib/utils";

export type ConfirmDialogAction = {
  label: string;
  onClick: () => void;
  variant?: "primary" | "danger" | "secondary";
  disabled?: boolean;
};

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  onClose: () => void;
  actions: ConfirmDialogAction[];
};

export function ConfirmDialog({
  open,
  title,
  message,
  onClose,
  actions,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-outline bg-surface shadow-2xl shadow-black/30">
        <div className="flex items-start justify-between gap-3 border-b border-outline px-5 py-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full border border-amber-500/20 bg-amber-500/10 p-2 text-amber-300">
              <AlertTriangle className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-primary">{title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-secondary">{message}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-secondary transition-colors hover:bg-surface-container-high hover:text-primary"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-wrap justify-end gap-2 px-5 py-4">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              disabled={action.disabled}
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                action.variant === "danger" &&
                  "bg-red-500/12 text-red-300 hover:bg-red-500/18 border border-red-500/20",
                action.variant === "primary" &&
                  "bg-primary/12 text-primary hover:bg-primary/18 border border-primary/20",
                (!action.variant || action.variant === "secondary") &&
                  "bg-surface-container text-primary hover:bg-surface-container-high border border-outline",
              )}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
