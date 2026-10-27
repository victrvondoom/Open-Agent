import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./pages/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "resolve-black": "var(--resolve-black)",
        "resolve-cream": "var(--resolve-cream)",
        "resolve-cream-panel": "var(--resolve-cream-panel)",
        "resolve-cream-dark": "var(--resolve-cream-dark)",
        "resolve-text": "var(--resolve-text)",
        "resolve-muted": "var(--resolve-muted)",
        "resolve-tertiary": "var(--resolve-tertiary)",
        "resolve-cyan": "var(--resolve-cyan)",
        "resolve-purple": "var(--resolve-purple)",
        "resolve-green": "var(--resolve-green)",
        "resolve-amber": "var(--resolve-amber)",
        "resolve-red": "var(--resolve-red)",
        "proxy-black": "var(--proxy-black)",
        "proxy-cream": "var(--proxy-cream)",
        "proxy-cream-panel": "var(--proxy-cream-panel)",
        "proxy-cream-dark": "var(--proxy-cream-dark)",
        "proxy-text": "var(--proxy-text)",
        "proxy-muted": "var(--proxy-muted)",
        "proxy-tertiary": "var(--proxy-tertiary)",
        "proxy-cyan": "var(--proxy-cyan)",
        "proxy-purple": "var(--proxy-purple)",
        "proxy-green": "var(--proxy-green)",
        "proxy-amber": "var(--proxy-amber)",
        "proxy-red": "var(--proxy-red)",
        glass: "var(--resolve-glass)",
        "pixel-border": "#231f1d",
      },
      fontFamily: {
        serif: ["var(--font-serif)", "EB Garamond", "Anthropic Serif", "Tiempos", "Georgia", "serif"],
        sans: ["var(--font-sans)", "Figtree", "Anthropic Sans", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        "pixel": "4px 4px 0px #231f1d",
        "pixel-sm": "2px 2px 0px #231f1d",
        "pixel-lg": "6px 6px 0px #231f1d",
        "glow-cyan": "4px 4px 0px #0284c7",
        "glow-purple": "4px 4px 0px #7c3aed",
        "glow-green": "4px 4px 0px #15803d",
      },
    },
  },
  plugins: [],
};

export default config;
