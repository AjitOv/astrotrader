import type { ConfluenceScore } from "@/lib/types";
import { pct, signedPct } from "@/lib/api";

interface Props { score: ConfluenceScore; }

const biasColor: Record<ConfluenceScore["bias"], string> = {
  bullish: "text-bull",
  bearish: "text-bear",
  neutral: "text-neutral",
};

const groupColor: Record<string, string> = {
  astro: "text-astro",
  market: "text-market",
  regime: "text-regime",
};

export function DecisionPanel({ score }: Props) {
  const arrow = score.bias === "bullish" ? "↑" : score.bias === "bearish" ? "↓" : "→";
  // Probability bar: bull green to the right, bear red to the left, anchored at 50%.
  const tilt = (score.p_up - 0.5) * 200; // -100..+100

  return (
    <section className="panel p-6">
      <div className="flex items-baseline justify-between mb-4">
        <div className="panel-label">Decision</div>
        <div className="text-[10px] text-bone-400 tracking-widest">
          horizon {score.horizon}d
        </div>
      </div>

      <div className="flex items-baseline gap-3 mb-3">
        <span className={`text-5xl font-light leading-none ${biasColor[score.bias]}`}>
          {arrow}
        </span>
        <div>
          <div className={`text-2xl font-light ${biasColor[score.bias]}`}>
            {score.bias.toUpperCase()}
          </div>
          <div className="text-xs text-bone-400 tracking-wide">
            P(up) {pct(score.p_up, 1)} · P(down) {pct(score.p_down, 1)}
            {score.calibrated && (
              <span className="ml-2 text-bone-400/70">
                [calibrated; raw {pct(score.p_up_raw, 1)}]
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Probability tilt bar */}
      <div className="relative h-2 rounded-full bg-ink-700 mt-5 mb-1 overflow-hidden">
        <div
          className={`absolute top-0 h-full ${
            tilt >= 0 ? "left-1/2 bg-bull/70" : "right-1/2 bg-bear/70"
          }`}
          style={{ width: `${Math.abs(tilt) / 2}%` }}
        />
        <div className="absolute left-1/2 top-0 h-full w-px bg-bone-400/40" />
      </div>
      <div className="flex justify-between text-[10px] text-bone-400">
        <span>bear</span>
        <span>50/50</span>
        <span>bull</span>
      </div>

      <hr className="border-white/5 my-5" />

      <div className="grid grid-cols-3 gap-4 text-sm">
        <Stat label="confidence" value={pct(score.confidence, 0)} />
        <Stat label="E[ret]" value={signedPct(score.expected_logret)} />
        <Stat label="E[realvol]" value={pct(score.expected_realvol, 1)} />
      </div>

      <div className="mt-5">
        <div className="panel-label mb-2">Component contributions</div>
        <ul className="space-y-1.5">
          {score.components.map((c) => (
            <li
              key={c.name}
              className="flex items-center gap-2 text-xs"
            >
              <span className={`w-16 ${groupColor[c.name]} tracking-wide`}>
                {c.name}
              </span>
              <span className="text-bone-400 w-12 tabular-nums">
                {c.contribution >= 0 ? "+" : ""}
                {c.contribution.toFixed(2)}pp
              </span>
              <ContribBar value={c.contribution} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="panel-label">{label}</div>
      <div className="text-bone-100 text-base mt-0.5 tabular-nums">{value}</div>
    </div>
  );
}

function ContribBar({ value }: { value: number }) {
  // ±5pp scale; clamp visually.
  const w = Math.min(Math.abs(value) / 5, 1) * 100;
  return (
    <div className="relative flex-1 h-1.5 bg-ink-700 rounded-full overflow-hidden">
      <div
        className={`absolute top-0 h-full ${value >= 0 ? "left-1/2 bg-bull/60" : "right-1/2 bg-bear/60"}`}
        style={{ width: `${w / 2}%` }}
      />
      <div className="absolute left-1/2 top-0 h-full w-px bg-white/10" />
    </div>
  );
}
