import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: {
            900: "#0E1F52",
            800: "#16327F",
            700: "#2B4FAE",
            500: "#85A3E3",
            300: "#C9DCF7",
            50: "#F0F4FC",
          },
          gold: {
            600: "#EFA10C",
            400: "#FDC02E",
            200: "#FFE39B",
          },
        },
      },
    },
  },
  plugins: [],
};

export default config;
