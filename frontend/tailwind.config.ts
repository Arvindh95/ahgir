import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#000000",
        primary: "#ffffff",
        secondary: "#a1a1aa", // zinc-400
        glass: "rgba(255, 255, 255, 0.05)",
        "glass-hover": "rgba(255, 255, 255, 0.1)",
        border: "rgba(255, 255, 255, 0.1)",
        // Lumière theme tokens
        lumiere: {
          bg: "#0e0b08",
          paper: "#181410",
          ink: "#efe3cb",
          "ink-dim": "#c9bca0",
          muted: "#7e705b",
          accent: "#d4a574",
          accent2: "#8b6f4e",
          border: "#2a211a",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
