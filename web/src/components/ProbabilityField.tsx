"use client";

import { scaleLinear } from "d3-scale";
import { extent } from "d3-array";
import type { HorizonOutcome, PriceTick } from "@/lib/types";
import { signedPct, pct } from "@/lib/api";

interface Props {
  horizons: HorizonOutcome[];
  recentPrices: PriceTick[];
  primaryHorizon: number;
  queryDate: string;
}

export function ProbabilityField({
  horizons,
  recentPrices,
  primaryHorizon,
  queryDate,
}: Props) {
  const W = 720;
  const H = 280;
  const margin = { top: 24, right: 80, bottom: 30, left: 50 };
  const innerW = W - margin.left - margin.right;
  const innerH = H - margin.top - margin.bottom;

  if (recentPrices.length < 2 || horizons.length === 0) return null;

  const last = recentPrices[recentPrices.length - 1].close;

  // x: trading day index (negative = past, positive = forward).
  // We center so x=0 is "now". Past extends -recentPrices.length..0; forward 0..maxHorizon.
  const horizonsSorted = [...horizons].sort((a, b) => a.horizon - b.horizon);
  const maxH = horizonsSorted[horizonsSorted.length - 1].horizon;

  const x = scaleLinear()
    .domain([-recentPrices.length + 1, maxH])
    .range([0, innerW]);

  // y in *relative log return from "now"*. Past prices contribute their own log
  // returns; forward quantiles contribute the q05..q95 spread per horizon.
  const pastLogRets = recentPrices.map((p) => Math.log(p.close / last));
  const fwdYs: number[] = [];
  horizonsSorted.forEach((h) => {
    fwdYs.push(h.quantiles.q05, h.quantiles.q95);
  });
  const yDomain = extent([...pastLogRets, ...fwdYs]) as [number, number];
  const padY = (yDomain[1] - yDomain[0]) * 0.15 || 0.005;

  const y = scaleLinear()
    .domain([yDomain[0] - padY, yDomain[1] + padY])
    .range([innerH, 0])
    .nice();

  // Past line path
  const pastPath =
    "M " +
    recentPrices
      .map((p, i) => {
        const xi = i - recentPrices.length + 1;
        return `${x(xi)},${y(Math.log(p.close / last))}`;
      })
      .join(" L ");

  // Forward cone polygons: outer (q05..q95), inner (q25..q75), and median line
  const outerTopPts: [number, number][] = [[x(0), y(0)]];
  const outerBotPts: [number, number][] = [[x(0), y(0)]];
  const innerTopPts: [number, number][] = [[x(0), y(0)]];
  const innerBotPts: [number, number][] = [[x(0), y(0)]];
  const medianPts: [number, number][] = [[x(0), y(0)]];

  for (const h of horizonsSorted) {
    outerTopPts.push([x(h.horizon), y(h.quantiles.q95)]);
    outerBotPts.push([x(h.horizon), y(h.quantiles.q05)]);
    innerTopPts.push([x(h.horizon), y(h.quantiles.q75)]);
    innerBotPts.push([x(h.horizon), y(h.quantiles.q25)]);
    medianPts.push([x(h.horizon), y(h.quantiles.q50)]);
  }

  const outerPath =
    "M " +
    outerTopPts.map((p) => p.join(",")).join(" L ") +
    " L " +
    [...outerBotPts].reverse().map((p) => p.join(",")).join(" L ") +
    " Z";

  const innerPath =
    "M " +
    innerTopPts.map((p) => p.join(",")).join(" L ") +
    " L " +
    [...innerBotPts].reverse().map((p) => p.join(",")).join(" L ") +
    " Z";

  const medianPath = "M " + medianPts.map((p) => p.join(",")).join(" L ");

  const primaryOutcome = horizons.find((h) => h.horizon === primaryHorizon);

  return (
    <section className="panel p-6">
      <div className="flex items-baseline justify-between mb-2">
        <div className="panel-label">Probability Field</div>
        <div className="text-[10px] text-bone-400 tracking-widest">
          past {recentPrices.length}d · forward to +{maxH}d
        </div>
      </div>
      <p className="text-xs text-bone-400 mb-3 max-w-2xl leading-relaxed">
        Shaded cones show the 25–75 (inner) and 5–95 (outer) percentile bands of the
        outcome distribution at each horizon, drawn from {horizonsSorted[0]?.n} similar
        past states. The dashed line is the median path.
      </p>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {/* y zero baseline */}
          <line
            x1={0}
            x2={innerW}
            y1={y(0)}
            y2={y(0)}
            className="tick-strong"
            strokeDasharray="2 4"
          />
          {/* "now" vertical */}
          <line
            x1={x(0)}
            x2={x(0)}
            y1={0}
            y2={innerH}
            stroke="rgba(255,255,255,0.25)"
          />
          <text
            x={x(0)}
            y={-8}
            textAnchor="middle"
            fontSize={9}
            fill="rgba(255,255,255,0.6)"
            letterSpacing={2}
          >
            NOW · {queryDate}
          </text>

          {/* Y ticks */}
          {y.ticks(5).map((t) => (
            <g key={t} transform={`translate(0, ${y(t)})`}>
              <line x1={0} x2={innerW} className="tick" strokeDasharray="1 3" />
              <text
                x={-8}
                y={3}
                textAnchor="end"
                fontSize={9}
                fill="rgba(255,255,255,0.45)"
                fontFamily="ui-monospace"
              >
                {signedPct(t, 1)}
              </text>
            </g>
          ))}

          {/* Forward cones */}
          <path d={outerPath} fill="rgba(34,211,238,0.10)" />
          <path d={innerPath} fill="rgba(34,211,238,0.20)" />
          <path
            d={medianPath}
            fill="none"
            stroke="rgba(34,211,238,0.7)"
            strokeWidth={1.4}
            strokeDasharray="3 3"
          />

          {/* Past path */}
          <path
            d={pastPath}
            fill="none"
            stroke="rgba(255,255,255,0.7)"
            strokeWidth={1.5}
          />

          {/* Endpoint marker for primary horizon */}
          {primaryOutcome && (
            <>
              <circle
                cx={x(primaryOutcome.horizon)}
                cy={y(primaryOutcome.quantiles.q50)}
                r={4}
                fill="#22d3ee"
              />
              <line
                x1={x(primaryOutcome.horizon)}
                x2={x(primaryOutcome.horizon)}
                y1={y(primaryOutcome.quantiles.q05)}
                y2={y(primaryOutcome.quantiles.q95)}
                stroke="#22d3ee"
                strokeOpacity={0.5}
              />
              <text
                x={x(primaryOutcome.horizon) + 8}
                y={y(primaryOutcome.quantiles.q50) - 4}
                fontSize={10}
                fill="#22d3ee"
                fontFamily="ui-monospace"
              >
                +{primaryOutcome.horizon}d · q50 {signedPct(primaryOutcome.quantiles.q50)}
              </text>
              <text
                x={x(primaryOutcome.horizon) + 8}
                y={y(primaryOutcome.quantiles.q50) + 12}
                fontSize={9}
                fill="rgba(255,255,255,0.55)"
                fontFamily="ui-monospace"
              >
                p_up {pct(primaryOutcome.p_up, 1)}
              </text>
            </>
          )}
        </g>
      </svg>

      {/* Horizon table */}
      <div className="mt-4 grid grid-cols-6 gap-2 text-[10px]">
        {horizonsSorted.map((h) => (
          <div
            key={h.horizon}
            className={`p-2 rounded-md border ${
              h.horizon === primaryHorizon
                ? "border-market/50 bg-market/5"
                : "border-white/5"
            }`}
          >
            <div className="text-bone-400 tracking-widest">+{h.horizon}D</div>
            <div className="text-bone-100 mt-0.5 tabular-nums">
              {signedPct(h.median_logret)}
            </div>
            <div className="text-bone-400 tabular-nums">
              p {pct(h.p_up, 0)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
