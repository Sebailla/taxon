/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Design tokens from Phase 3 (taxon.pen).
      // The .pen uses $accent / $bg / $border / $muted / $navy / $red /
      // $slate / $surface / $amber as semantic colors. Tailwind maps them
      // below; the React components use these names so the code mirrors
      // the design.
      colors: {
        accent: "#3b82f6",
        amber: "#d97706",
        bg: "#f8fafc",
        border: "#e2e8f0",
        muted: "#94a3b8",
        navy: "#0f172a",
        slate: "#475569",
        red: "#dc2626",
        surface: "#ffffff",
        // Subtle backgrounds for marker badges (replaces the 10
        // hard-coded hex values from the .pen design).
        "red-50": "#fef2f2",
        "amber-50": "#fffbeb",
        "green-50": "#f0fdf4",
        "blue-50": "#eff6ff",
      },
      fontFamily: {
        // P3 follow-up from the audit: system-ui wins before Inter
        // loads, so the user's OS font is preferred.
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Inter",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "IBM Plex Mono",
          "monospace",
        ],
      },
      borderRadius: {
        chip: "4px",
        btn: "8px",
        card: "12px",
      },
      maxWidth: {
        page: "1200px",
      },
    },
  },
  plugins: [],
};