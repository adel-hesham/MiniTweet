export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#5B5BF0", dark: "#4747D6" },
        accent: "#FF6B5B",
        surface: { DEFAULT: "#F7F8FC", dark: "#0B0F1A" },
        card: { DEFAULT: "#FFFFFF", dark: "#121828" },
        ink: { DEFAULT: "#111827", dark: "#E5E7EB" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        heading: ['"Plus Jakarta Sans"', "Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
