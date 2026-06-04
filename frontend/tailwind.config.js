/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        af: {
          blue:     '#00A1E0',
          purple:   '#7C3AED',
          charcoal: '#1E293B',
          slate:    '#E8EEF8',
          ink:      '#0F172A',
          darkbg:   '#0B0F19',
          darkcard: '#161F30',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ['Outfit', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
