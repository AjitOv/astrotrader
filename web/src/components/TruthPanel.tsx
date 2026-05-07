import type { ConfluenceScore, HorizonOutcome } from "@/lib/types";
import { pct, fmt } from "@/lib/api";

interface Props {
  score: ConfluenceScore;
  horizons: HorizonOutcome[];
}

export function TruthPanel({ score, horizons }: Props) {
  const primary = horizons.find((h) => h.horizon === score.horizon);
  const baseRateProxy = primary ? primary.p_up : 0.5;
  const tilt = score.p_up - baseRateProxy;

  return (
    <section className="panel p-6">
      <div className="flex items-baseline justify-between mb-3">
        <div className="panel-label">Truth Panel</div>
        <div className="text-[10px] text-bone-400 tracking-widest">no hiding</div>
      </div>

      <ul className="space-y-2 text-xs">
        <Row
          label="sample size (N)"
          value={`${score.sample_size}`}
          help="Number of past states that contributed to the outcome distribution."
        />
        <Row
          label="effective N (Kish)"
          value={fmt(score.effective_sample_size, 1)}
          help="Sum-of-weights² adjusted N. If this is much smaller than N, a few states are doing all the work."
        />
        <Row
          label="calibrated"
          value={score.calibrated ? "yes (isotonic/Platt)" : "no — raw similarity vote"}
          help="Calibrated probabilities have been corrected to match historical realized frequencies."
        />
        <Row
          label="raw P(up)"
          value={pct(score.p_up_raw, 1)}
          help="The pre-calibration probability. Compare to the calibrated number to see how much the calibrator moved the call."
        />
        <Row
          label="tilt vs sample mean"
          value={`${tilt >= 0 ? "+" : ""}${(tilt * 100).toFixed(2)}pp`}
          help="How much the calibrated probability differs from the raw weighted vote at the primary horizon."
        />
      </ul>

      <hr className="border-white/5 my-4" />

      <div className="text-[11px] text-bone-400 leading-relaxed space-y-1.5">
        <p>
          This system <span className="text-bone-200">does not predict price.</span>{" "}
          It returns a probability distribution over forward outcomes, conditioned on
          how often similar past moments resolved each way.
        </p>
        <p>
          Past performance ≠ future. Even calibrated probabilities can be wrong on any
          single trial. The system&apos;s value compounds across many decisions, not on any one.
        </p>
      </div>
    </section>
  );
}

function Row({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <li className="grid grid-cols-[170px_1fr] gap-3 items-start">
      <span className="panel-label !lowercase tracking-wide">{label}</span>
      <div>
        <div className="text-bone-100 tabular-nums">{value}</div>
        <div className="text-[10px] text-bone-400 mt-0.5 leading-snug">{help}</div>
      </div>
    </li>
  );
}
