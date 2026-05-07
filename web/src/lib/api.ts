import type { DecideRequest, DecideResponse } from "./types";

// Server-only env var (no NEXT_PUBLIC prefix) — keeps the engine URL out of the
// client bundle. Set ASTROTRADE_API_URL in Vercel to your Render deploy URL.
const API_BASE = process.env.ASTROTRADE_API_URL ?? "http://127.0.0.1:8000";

// Render free tier sleeps after 15min idle and takes ~30s to wake. We leave
// generous headroom for the first request after a cold start.
const TIMEOUT_MS = Number(process.env.ASTROTRADE_API_TIMEOUT_MS ?? 60_000);

export async function decide(req: DecideRequest): Promise<DecideResponse> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      cache: "no-store",
      signal: ac.signal,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`decide failed (${res.status}): ${detail}`);
    }
    return res.json();
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error(
        `decide timed out after ${TIMEOUT_MS / 1000}s — backend is likely still ` +
          `building this symbol's state matrix. Refresh in a moment.`,
      );
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export function pct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function signedPct(x: number, digits = 2): string {
  const sign = x >= 0 ? "+" : "";
  return `${sign}${(x * 100).toFixed(digits)}%`;
}

export function fmt(x: number, digits = 2): string {
  return x.toFixed(digits);
}
