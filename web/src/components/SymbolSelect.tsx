"use client";

import { useEffect, useRef, useState } from "react";
import { SYMBOL_GROUPS, findSymbolMeta } from "@/lib/types";

interface Props {
  value: string;
  onChange: (next: string) => void;
}

export function SymbolSelect({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click and on Escape — kept lightweight, no portal needed.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = findSymbolMeta(value);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-baseline gap-2 px-3 py-1.5 rounded-md border border-white/10 bg-white/5 hover:border-white/20 text-bone-100 text-xs tabular-nums"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="panel-label !lowercase tracking-wide text-bone-400">
          symbol
        </span>
        <span className="font-medium tracking-wider">{value}</span>
        {current && (
          <span className="text-[10px] text-bone-400 hidden sm:inline">
            · {current.meta.hint}
          </span>
        )}
        <span className="text-bone-400 text-[10px] ml-1">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute right-0 top-full mt-1.5 z-30 w-[300px] panel p-2 shadow-2xl border border-white/10"
        >
          {SYMBOL_GROUPS.map((group) => (
            <div key={group.category} className="mb-2 last:mb-0">
              <div className="panel-label px-2 py-1.5">{group.category}</div>
              <ul className="space-y-0.5">
                {group.symbols.map((s) => {
                  const active = s.symbol === value;
                  return (
                    <li key={s.symbol}>
                      <button
                        onClick={() => {
                          onChange(s.symbol);
                          setOpen(false);
                        }}
                        className={`w-full text-left px-2 py-1.5 rounded-md text-xs flex items-baseline gap-2 transition-colors ${
                          active
                            ? "bg-bone-200/10 text-bone-100"
                            : "hover:bg-white/5 text-bone-200"
                        }`}
                      >
                        <span
                          className={`w-1 h-1 rounded-full ${
                            active ? "bg-market" : "bg-transparent"
                          }`}
                        />
                        <span className="font-medium tracking-wider w-24 tabular-nums">
                          {s.symbol}
                        </span>
                        <span className="text-[10px] text-bone-400 truncate">
                          {s.hint}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
