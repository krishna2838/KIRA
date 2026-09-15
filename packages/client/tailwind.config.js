/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        kira: {
          bg: "#0a0a0a",
          panel: "#111113",
          border: "#1f1f22",
          text: "#e5e5e7",
          muted: "#8a8a92",
          accent: "#06b6d4",
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
