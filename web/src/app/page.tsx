import { Suspense } from "react";
import { decide } from "@/lib/api";
import { ClockPanel } from "@/components/ClockPanel";
import { DecisionPanel } from "@/components/DecisionPanel";
import { MirrorPanel } from "@/components/MirrorPanel";
import { ProbabilityField } from "@/components/ProbabilityField";
import { TruthPanel } from "@/components/TruthPanel";
import { Controls } from "@/components/Controls";
import { DashboardSkeleton } from "@/components/DashboardSkeleton";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ symbol?: string; horizon?: string }>;
}

// The shell renders instantly. Header (with Controls) is outside the Suspense
// boundary so symbol/horizon switching feels responsive even while the engine
// builds a fresh context. The Dashboard component does the slow `decide()` call
// and is wrapped in <Suspense> so it streams in.
export default async function Home(props: PageProps) {
  const sp = await props.searchParams;
  const symbol = (sp.symbol ?? "SPY").toUpperCase();
  const horizon = Number(sp.horizon ?? 5);

  return (
    <main className="relative min-h-screen px-8 py-6 max-w-[1600px] mx-auto">
      <header className="flex items-center justify-between mb-6 relative z-10">
        <div className="flex items-baseline gap-4">
          <h1 className="text-bone-100 text-lg tracking-[0.2em] font-light">
            ASTROTRADE
          </h1>
          <span className="text-[10px] text-bone-400 tracking-widest">
            TIME INTELLIGENCE ENGINE
          </span>
        </div>
        <Suspense fallback={null}>
          <Controls symbol={symbol} horizon={horizon} />
        </Suspense>
      </header>

      <Suspense
        key={`${symbol}-${horizon}`}
        fallback={<DashboardSkeleton symbol={symbol} horizon={horizon} />}
      >
        <Dashboard symbol={symbol} horizon={horizon} />
      </Suspense>

      <footer className="mt-10 text-[10px] text-bone-400 tracking-widest text-center">
        ephemeris: NASA JPL DE440s · prices: yfinance
      </footer>
    </main>
  );
}

async function Dashboard({ symbol, horizon }: { symbol: string; horizon: number }) {
  let data;
  let error: string | null = null;
  try {
    data = await decide({ symbol, horizon, top_n: 50 });
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || !data) return <ErrorBox error={error ?? "no data"} />;

  return (
    <div className="grid grid-cols-12 gap-5">
      <div className="col-span-5">
        <ClockPanel ephemeris={data.ephemeris} queryDate={data.query_date} />
      </div>
      <div className="col-span-4 space-y-5">
        <DecisionPanel score={data.score} />
        <TruthPanel score={data.score} horizons={data.horizons} />
      </div>
      <div className="col-span-3">
        <SymbolBadge
          symbol={data.symbol}
          date={data.query_date}
          calibrated={data.score.calibrated}
        />
      </div>
      <div className="col-span-12">
        <ProbabilityField
          horizons={data.horizons}
          recentPrices={data.recent_prices}
          primaryHorizon={horizon}
          queryDate={data.query_date}
        />
      </div>
      <div className="col-span-12">
        <MirrorPanel matches={data.matches} queryDate={data.query_date} />
      </div>
    </div>
  );
}

function ErrorBox({ error }: { error: string }) {
  return (
    <div className="panel p-6 border-bear/30">
      <div className="panel-label text-bear">backend unreachable</div>
      <p className="text-sm text-bone-200 mt-2">
        Could not reach the ASTROTRADE engine on{" "}
        <code className="text-market">127.0.0.1:8000</code>.
      </p>
      <p className="text-xs text-bone-400 mt-1.5">
        Start it with{" "}
        <code className="text-bone-200">
          .venv/bin/uvicorn astrotrader.api.main:app --port 8000
        </code>{" "}
        from the project root.
      </p>
      <pre className="text-[10px] text-bone-400 mt-3 whitespace-pre-wrap font-mono">
        {error}
      </pre>
    </div>
  );
}

function SymbolBadge({
  symbol,
  date,
  calibrated,
}: {
  symbol: string;
  date: string;
  calibrated: boolean;
}) {
  return (
    <section className="panel p-6 h-full flex flex-col justify-between">
      <div>
        <div className="panel-label">Subject</div>
        <div className="text-5xl font-light tracking-tight mt-3">{symbol}</div>
        <div className="text-xs text-bone-400 mt-1 tabular-nums">{date}</div>
      </div>
      <div className="space-y-1.5 text-[10px] text-bone-400 mt-6">
        <Pip on={calibrated} label={calibrated ? "calibrated" : "uncalibrated"} />
        <Pip on label="walk-forward eval" />
        <Pip on label="leakage guarded" />
        <Pip on={false} label="UI v0.2" />
      </div>
    </section>
  );
}

function Pip({ on, label }: { on: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${
          on ? "bg-bull/80" : "bg-bone-400/40"
        }`}
      />
      <span className="tracking-widest uppercase">{label}</span>
    </div>
  );
}
