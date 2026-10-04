/** @type {import('tailwindcss').Config} */
export default {
  content: ["./frontend/index.html", "./frontend/src/**/*.{js,ts,jsx,tsx}"],
  corePlugins: {
    // Existing SANKET styling is retained without Tailwind's global reset.
    preflight: false,
  },
  theme: {
    extend: {},
  },
  plugins: [],
};
