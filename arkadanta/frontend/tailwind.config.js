/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        obsidian: '#070b14',
        panel: '#0f172a',
        panelLight: '#1e293b',
      },
    },
  },
  plugins: [],
};
