import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0D0D0D",
        card: "#141414",
        border: "#222222",
        primaryText: "#F0F0F0",
        secondaryText: "#666666",
        riskHigh: "#EF4444",
        riskMid: "#F59E0B",
        riskLow: "#22C55E",
      },
    },
  },
  plugins: [],
};

export default config;
