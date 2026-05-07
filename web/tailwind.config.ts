import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      colors: {
        // "looking at time" — deep ink, signal lines, single accent.
        ink: {
          950: "#06070a",
          900: "#0b0d12",
          800: "#10131a",
          700: "#181c25",
          600: "#222734",
          500: "#2c3344",
          400: "#3d4659",
        },
        bone: {
          400: "#9aa1ad",
          300: "#c5cad4",
          200: "#dfe2e8",
          100: "#eef0f4",
        },
        // Semantic — bias only. Single hue per direction so the eye learns it fast.
        bull: "#4ade80",
        bear: "#f87171",
        neutral: "#94a3b8",
        // Astro/market/regime triad.
        astro: "#a78bfa",
        market: "#22d3ee",
        regime: "#fbbf24",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(255,255,255,0.04), inset 0 0 60px rgba(255,255,255,0.02)",
      },
    },
  },
  plugins: [],
};

export default config;
