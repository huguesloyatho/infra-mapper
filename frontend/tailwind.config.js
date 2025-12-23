/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'host': '#3b82f6',
        'container-running': '#22c55e',
        'container-stopped': '#ef4444',
        'container-paused': '#f59e0b',
        'external': '#8b5cf6',
        'connection': '#6b7280',
        'dependency': '#06b6d4',
      },
    },
  },
  plugins: [],
}
