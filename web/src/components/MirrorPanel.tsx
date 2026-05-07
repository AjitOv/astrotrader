import type { Match, FeatureGroup } from "@/lib/types";

interface Props {
  matches: Match[];
  queryDate: string;
  limit?: number;
}

const GROUPS: FeatureGroup[] = ["astro", "market", "regime"];
const groupColor: Record<FeatureGroup, string> = {
  astro: "bg-astro",
  market: "bg-market",
  regime: "bg-regime",
};

export function MirrorPanel({ matches, queryDate, limit = 12 }: Props) {
  const top = matches.slice(0, limit);
  return (
    <section className="panel p-6">
      <div className="flex items-baseline justify-between mb-2">
        <div className="panel-label">The Mirror</div>
        <div className="text-[10px] text-bone-400 tracking-widest">
          {top.length} most similar moments to {queryDate}
        </div>
      </div>
      <p className="text-xs text-bone-400 mb-4 max-w-md leading-relaxed">
        Each row is a date in history when reality was geometrically and structurally
        similar to today. Per-group bars show <em>why</em> they matched.
      </p>

      <ul className="space-y-2">
        {top.map((m) => (
          <li
            key={m.date}
            className="grid grid-cols-[110px_60px_1fr] gap-3 items-center text-xs"
          >
            <span className="text-bone-200 tabular-nums">{m.date}</span>
            <span className="text-bone-100 tabular-nums">
              {m.similarity >= 0 ? "+" : ""}
              {m.similarity.toFixed(3)}
            </span>
            <div className="flex gap-1.5 items-center">
              {GROUPS.map((g) => {
                const v = m.per_group[g];
                // Map [-1, +1] → [0, 100%]; we only show positive direction filled.
                const width = Math.max(0, v) * 100;
                return (
                  <div key={g} className="flex-1">
                    <div className="h-1.5 bg-ink-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${groupColor[g]} opacity-80`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                    <div className="text-[9px] text-bone-400 mt-0.5 flex justify-between">
                      <span className="tracking-widest uppercase">{g[0]}</span>
                      <span className="tabular-nums">{v.toFixed(2)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
