// Mirrors the JSON returned by FastAPI POST /decide.
// Single source of typed truth for every component.

export type FeatureGroup = "astro" | "market" | "regime";

export interface ScoreComponent {
  name: string;
  contribution: number; // probability points
  detail: string;
}

export interface ConfluenceScore {
  horizon: number;
  bias: "bullish" | "bearish" | "neutral";
  p_up: number;
  p_up_raw: number;
  p_down: number;
  confidence: number;
  expected_logret: number;
  expected_realvol: number;
  calibrated: boolean;
  components: ScoreComponent[];
  sample_size: number;
  effective_sample_size: number;
}

export interface HorizonOutcome {
  horizon: number;
  n: number;
  weighted_n: number;
  mean_logret: number;
  median_logret: number;
  std_logret: number;
  p_up: number;
  p_down: number;
  quantiles: Record<"q05" | "q25" | "q50" | "q75" | "q95", number>;
  expected_maxdd: number;
  expected_maxup: number;
  expected_realvol: number;
}

export interface Match {
  date: string; // YYYY-MM-DD
  similarity: number;
  per_group: Record<FeatureGroup, number>;
}

export interface BodyPosition {
  longitude: number; // degrees, 0..360
  speed: number;     // deg/day
  retrograde: boolean;
}

export interface PriceTick {
  date: string;
  close: number;
}

export interface DecideResponse {
  symbol: string;
  query_date: string;
  score: ConfluenceScore;
  horizons: HorizonOutcome[];
  matches: Match[];
  ephemeris: Record<string, BodyPosition>;
  recent_prices: PriceTick[];
}

export interface DecideRequest {
  symbol: string;
  horizon: number;
  date?: string | null;
  top_n?: number | null;
}

export const HORIZONS = [1, 3, 5, 10, 21, 63] as const;

/** Asset-class-grouped symbol catalogue. Order inside each group is by liquidity. */
export interface SymbolMeta {
  symbol: string;     // user-facing label, also passed to the API
  display?: string;   // optional pretty name in the dropdown (defaults to symbol)
  hint?: string;      // a short description shown under the symbol in the dropdown
}

export interface SymbolGroup {
  category: string;
  symbols: SymbolMeta[];
}

export const SYMBOL_GROUPS: SymbolGroup[] = [
  {
    category: "US Equities",
    symbols: [
      { symbol: "SPY", hint: "S&P 500 ETF" },
      { symbol: "QQQ", hint: "Nasdaq-100 ETF" },
      { symbol: "IWM", hint: "Russell 2000 ETF" },
    ],
  },
  {
    category: "Commodities",
    symbols: [
      { symbol: "GLD",    hint: "Gold ETF" },
      { symbol: "USO",    hint: "Oil ETF" },
      { symbol: "XAUUSD", hint: "Gold spot (futures)" },
    ],
  },
  {
    category: "India",
    symbols: [
      { symbol: "NIFTY",     hint: "NSE Nifty 50 index" },
      { symbol: "BANKNIFTY", hint: "NSE Bank Nifty index" },
      { symbol: "RELIANCE",  hint: "Reliance Industries (NSE)" },
      { symbol: "TCS",       hint: "Tata Consultancy Services (NSE)" },
      { symbol: "HDFCBANK",  hint: "HDFC Bank (NSE)" },
    ],
  },
  {
    category: "Crypto",
    symbols: [
      { symbol: "BTCUSD", hint: "Bitcoin / USD" },
      { symbol: "ETHUSD", hint: "Ethereum / USD" },
    ],
  },
];

/** Flat list — mostly for type-narrowing. */
export const SYMBOLS = SYMBOL_GROUPS.flatMap((g) => g.symbols.map((s) => s.symbol));

export function findSymbolMeta(symbol: string): { meta: SymbolMeta; category: string } | null {
  for (const g of SYMBOL_GROUPS) {
    const m = g.symbols.find((s) => s.symbol === symbol);
    if (m) return { meta: m, category: g.category };
  }
  return null;
}
