"use client";

import { useEffect, useState } from "react";
import type { BodyPosition } from "@/lib/types";

interface Props {
  ephemeris: Record<string, BodyPosition>;
  queryDate: string;
}

const BODY_ORDER = [
  "sun",  "moon", "mercury", "venus", "mars",
  "jupiter", "saturn", "uranus", "neptune", "pluto",
] as const;

const GLYPH: Record<string, string> = {
  sun: "☉", moon: "☾", mercury: "☿", venus: "♀", mars: "♂",
  jupiter: "♃", saturn: "♄", uranus: "♅", neptune: "♆", pluto: "♇",
};

const SIGNS = [
  "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
  "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
];

// 0° = Aries on the right; rotated −90° so 0° lands at 12-o'clock.
function lonToXY(lon: number, r: number): [number, number] {
  const rad = ((lon - 90) * Math.PI) / 180;
  return [r * Math.cos(rad), r * Math.sin(rad)];
}

export function ClockPanel({ ephemeris, queryDate }: Props) {
  const size = 380;
  const c = size / 2;
  const rOuter = c - 14;
  const rZodiac = rOuter - 18;
  const rPlanet = rZodiac - 24;
  const rInner = rPlanet - 30;

  // Trigger the entry animation only once per mount. The class is removed
  // after the animation finishes so subsequent re-renders glide via
  // .planet-glide instead of replaying the settle animation.
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSettled(true), 900);
    return () => clearTimeout(t);
  }, []);

  // Spread planets by radius when bodies cluster within 6° of each other.
  const placed = BODY_ORDER.map((b) => ({ name: b, ...ephemeris[b] }));
  const planetRows = placed.map((p, i) => {
    let radius = rPlanet;
    for (let j = 0; j < i; j++) {
      const diff = Math.abs(((p.longitude - placed[j].longitude + 540) % 360) - 180);
      if (diff < 6) radius -= 12 * (j + 1 - i);
    }
    return { ...p, radius };
  });

  const [sunX, sunY] = lonToXY(ephemeris.sun.longitude, rPlanet - 4);

  return (
    <section className="panel p-6">
      <div className="flex items-baseline justify-between mb-2">
        <div className="panel-label">The Clock</div>
        <div className="text-[10px] text-bone-400 tracking-widest">
          {queryDate} · geocentric ecliptic
        </div>
      </div>

      <div className="flex justify-center">
        <svg viewBox={`${-c} ${-c} ${size} ${size}`} width={size} height={size}>
          {/* Decorative slow-rotating star ring (background only — readable
              labels and ticks stay still). */}
          <g className="clock-rotate-slow" style={{ transformOrigin: "0 0" }}>
            {Array.from({ length: 60 }).map((_, i) => {
              const ang = (i / 60) * 360;
              const r = rInner - 8 - (i % 3) * 4;
              const [x, y] = lonToXY(ang, r);
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r={i % 5 === 0 ? 0.8 : 0.5}
                  fill="rgba(255,255,255,0.20)"
                />
              );
            })}
          </g>

          {/* Concentric reference rings */}
          <circle r={rOuter} fill="none" className="tick" strokeWidth={1} />
          <circle r={rZodiac} fill="none" className="tick" strokeWidth={1} />
          <circle r={rInner} fill="none" className="tick-strong" strokeWidth={1} />

          {/* 12 zodiac dividers + names */}
          {SIGNS.map((sign, i) => {
            const lon = i * 30;
            const [x1, y1] = lonToXY(lon, rZodiac);
            const [x2, y2] = lonToXY(lon, rOuter);
            const [tx, ty] = lonToXY(lon + 15, rZodiac + 9);
            return (
              <g key={sign}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} className="tick" strokeWidth={1} />
                <text
                  x={tx}
                  y={ty}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={9}
                  fill="rgba(255,255,255,0.45)"
                  fontFamily="ui-monospace, monospace"
                  letterSpacing={1}
                >
                  {sign.slice(0, 3).toUpperCase()}
                </text>
              </g>
            );
          })}

          {/* 5° minor ticks */}
          {Array.from({ length: 72 }, (_, i) => i * 5).map((d) => {
            const [x1, y1] = lonToXY(d, rOuter - 4);
            const [x2, y2] = lonToXY(d, rOuter);
            return (
              <line
                key={d}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={d % 30 === 0 ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.12)"}
                strokeWidth={1}
              />
            );
          })}

          {/* "Now hand": Earth → Sun. The cosmic hour hand. */}
          <line
            x1={0}
            y1={0}
            x2={sunX}
            y2={sunY}
            stroke="rgba(251,191,36,0.7)"
            strokeWidth={1.2}
            strokeDasharray="0"
            className="now-hand"
          />

          {/* Aspect lines — they breathe to suggest "active" geometry. */}
          {strongAspects(planetRows).map((a, i) => {
            const [x1, y1] = lonToXY(a.l1, rPlanet - 14);
            const [x2, y2] = lonToXY(a.l2, rPlanet - 14);
            return (
              <line
                key={`${a.l1}-${a.l2}-${i}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={a.color}
                strokeWidth={1}
                strokeDasharray={a.dash}
                className="aspect-breathe"
                style={{ animationDelay: `${(i * 0.4) % 3}s` }}
              />
            );
          })}

          {/* Planet glyphs — stable keys per body so React reconciles the
              same <g> across data updates and CSS transitions on transform
              create the glide effect. */}
          {planetRows.map((p, i) => {
            const [x, y] = lonToXY(p.longitude, p.radius);
            const isLuminary = p.name === "sun" || p.name === "moon";
            const settleClass = settled ? "" : "planet-settle";
            return (
              <g
                key={p.name}
                transform={`translate(${x}, ${y})`}
                className={`planet-glide ${settleClass}`}
                style={!settled ? { animationDelay: `${i * 50}ms` } : undefined}
              >
                {/* line from outer ring to planet */}
                <line
                  x1={(lonToXY(p.longitude, rOuter - 6)[0] - x)}
                  y1={(lonToXY(p.longitude, rOuter - 6)[1] - y)}
                  x2={0}
                  y2={0}
                  stroke="rgba(255,255,255,0.18)"
                  strokeWidth={1}
                />
                <circle
                  cx={0}
                  cy={0}
                  r={isLuminary ? 9 : 7}
                  fill="#0b0d12"
                  stroke={p.retrograde ? "#f87171" : "rgba(255,255,255,0.6)"}
                  strokeWidth={1.2}
                />
                <text
                  x={0}
                  y={0.5}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={isLuminary ? 13 : 11}
                  fill={p.retrograde ? "#f87171" : "#dfe2e8"}
                >
                  {GLYPH[p.name]}
                </text>
              </g>
            );
          })}

          {/* Earth pulse at center */}
          <circle r={3} fill="rgba(255,255,255,0.55)" className="earth-pulse" />
          <text
            x={0}
            y={rInner - 6}
            textAnchor="middle"
            fontSize={8}
            fill="rgba(255,255,255,0.45)"
            letterSpacing={2}
          >
            EARTH
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-bone-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-px bg-bull/70" /> trine 120°
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-px bg-bear/70" /> square 90°
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-px bg-bone-400" /> opposition 180°
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-1.5 h-1.5 rounded-full border border-bear" /> retrograde
        </span>
        <span className="flex items-center gap-1.5 ml-auto text-regime/80">
          <span className="inline-block w-3 h-px bg-regime/70" /> Earth → Sun
        </span>
      </div>
    </section>
  );
}

interface AspectLine {
  l1: number;
  l2: number;
  color: string;
  dash: string;
}

function strongAspects(
  bodies: { name: string; longitude: number; retrograde: boolean }[],
): AspectLine[] {
  const ASPECTS: { angle: number; color: string; dash: string; orb: number }[] = [
    { angle: 120, color: "#4ade80", dash: "0", orb: 4 }, // trine
    { angle: 90,  color: "#f87171", dash: "0", orb: 4 }, // square
    { angle: 180, color: "#9aa1ad", dash: "2 3", orb: 5 }, // opposition
    { angle: 0,   color: "#fbbf24", dash: "0", orb: 4 }, // conjunction
  ];

  const lines: AspectLine[] = [];
  const set = bodies.filter((b) => b.name !== "moon").slice(0, 9);
  for (let i = 0; i < set.length; i++) {
    for (let j = i + 1; j < set.length; j++) {
      const diff = ((set[i].longitude - set[j].longitude + 540) % 360) - 180;
      const adiff = Math.abs(diff);
      for (const a of ASPECTS) {
        if (Math.abs(adiff - a.angle) <= a.orb) {
          lines.push({
            l1: set[i].longitude,
            l2: set[j].longitude,
            color: a.color,
            dash: a.dash,
          });
          break;
        }
      }
    }
  }
  return lines;
}
