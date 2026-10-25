import { useEffect, useRef, useState, type ComponentType } from "react";
import { Ellipsis } from "lucide-react";
import { cn } from "../lib/utils";

export type OverflowMenuItem = {
  label: string;
  icon: ComponentType<{ className?: string }>;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
};

/** Icon button that opens a small action list; closes on selection, outside click, or Escape. */
export function OverflowMenu({
  label,
  items,
  placement = "below",
}: {
  label: string;
  items: OverflowMenuItem[];
  placement?: "below" | "above";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-secondary transition-colors hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-amber/50"
      >
        <Ellipsis className="h-4 w-4" />
      </button>
      {open ? (
        <div
          role="menu"
          className={cn(
            "absolute right-0 z-40 w-52 rounded-xl border border-outline bg-modal p-1 shadow-lg backdrop-blur-xl",
            placement === "above" ? "bottom-11" : "top-11",
          )}
        >
          {items.map(({ label: itemLabel, icon: Icon, onSelect, danger, disabled }) => (
            <button
              key={itemLabel}
              type="button"
              role="menuitem"
              disabled={disabled}
              onClick={() => {
                setOpen(false);
                onSelect();
              }}
              className={cn(
                "flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-left text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                danger
                  ? "text-red-600 hover:bg-red-500/10 dark:text-red-300"
                  : "text-primary hover:bg-primary/5",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {itemLabel}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
