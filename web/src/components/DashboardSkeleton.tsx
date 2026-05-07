// Renders the same 12-col grid as the real Dashboard, with shimmer placeholders.
// Painted instantly while the FastAPI engine warms up the StateMatrix.

export function DashboardSkeleton({
  symbol,
  horizon,
}: {
  symbol: string;
  horizon: number;
}) {
  return (
    <div className="grid grid-cols-12 gap-5">
      <div className="col-span-5">
        <SkelPanel label="The Clock" height={420} />
      </div>
      <div className="col-span-4 space-y-5">
        <SkelPanel label="Decision" height={260} />
        <SkelPanel label="Truth Panel" height={300} />
      </div>
      <div className="col-span-3">
        <SkelSubject symbol={symbol} horizon={horizon} />
      </div>
      <div className="col-span-12">
        <SkelPanel label="Probability Field" height={340} />
      </div>
      <div className="col-span-12">
        <SkelPanel label="The Mirror" height={420} />
      </div>
    </div>
  );
}

function SkelPanel({ label, height }: { label: string; height: number }) {
  return (
    <section className="panel p-6 relative overflow-hidden">
      <div className="flex items-baseline justify-between mb-3">
        <div className="panel-label">{label}</div>
        <div className="text-[10px] text-bone-400 tracking-widest animate-pulse">
          warming engine…
        </div>
      </div>
      <div style={{ height }} className="relative">
        <div className="absolute inset-0 flex items-center justify-center">
          <Pulse />
        </div>
        {/* Faint horizontal placeholder bars to suggest content density. */}
        <div className="absolute inset-x-0 top-1/4 space-y-3 px-8 opacity-30">
          <SkelBar w="60%" />
          <SkelBar w="80%" />
          <SkelBar w="45%" />
          <SkelBar w="70%" />
        </div>
      </div>
    </section>
  );
}

function SkelBar({ w }: { w: string }) {
  return (
    <div
      className="h-2 rounded-full bg-bone-400/10 animate-pulse"
      style={{ width: w }}
    />
  );
}

function SkelSubject({ symbol, horizon }: { symbol: string; horizon: number }) {
  return (
    <section className="panel p-6 h-full flex flex-col justify-between">
      <div>
        <div className="panel-label">Subject</div>
        <div className="text-5xl font-light tracking-tight mt-3">{symbol}</div>
        <div className="text-xs text-bone-400 mt-1 tabular-nums">
          horizon {horizon}d
        </div>
      </div>
      <div className="text-[10px] text-bone-400 tracking-widest mt-6 animate-pulse">
        building state matrix…
      </div>
    </section>
  );
}

// Slow-rotating ring + tick marks. Pure CSS, no JS — survives partial hydration.
function Pulse() {
  return (
    <div className="relative w-20 h-20">
      <div className="absolute inset-0 rounded-full border border-bone-400/20" />
      <div className="absolute inset-2 rounded-full border border-bone-400/15" />
      <div
        className="absolute inset-0 rounded-full border-t border-market/60 animate-spin"
        style={{ animationDuration: "3s" }}
      />
    </div>
  );
}
