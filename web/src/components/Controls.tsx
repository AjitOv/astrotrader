"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { HORIZONS } from "@/lib/types";
import { SymbolSelect } from "./SymbolSelect";

export function Controls({ symbol, horizon }: { symbol: string; horizon: number }) {
  const router = useRouter();
  const params = useSearchParams();

  const update = (key: "symbol" | "horizon", value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/?${next.toString()}`);
  };

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <span className="panel-label">horizon</span>
        <div className="flex gap-1">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => update("horizon", String(h))}
              className={`px-2.5 py-1 text-xs rounded-md border transition-colors tabular-nums ${
                h === horizon
                  ? "border-bone-200/50 bg-bone-200/10 text-bone-100"
                  : "border-white/10 text-bone-400 hover:border-white/20 hover:text-bone-200"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>
      <SymbolSelect value={symbol} onChange={(s) => update("symbol", s)} />
    </div>
  );
}
