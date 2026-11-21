import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        soc: {
          bg: "#070b14",       // page background
          panel: "#0c1322",    // cards
          panel2: "#111b30",   // raised surfaces, inputs on hover
          border: "#1c2742",
          muted: "#8b9ab8",
          accent: "#38bdf8",
        },
      },
      fontFamily: {
        // System fonts only (nothing is downloaded): Inter if installed, Segoe UI Variable on Windows 11.
        sans: ["Inter", "Segoe UI Variable Text", "Segoe UI", "system-ui", "-apple-system", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "inset 0 1px 0 0 rgba(255,255,255,0.035), 0 10px 30px -18px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(56,189,248,0.35), 0 8px 24px -10px rgba(56,189,248,0.45)",
      },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
