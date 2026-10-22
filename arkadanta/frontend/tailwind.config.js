/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Poppins', 'Inter', '-apple-system', 'sans-serif'],
      },
      colors: {
        // Black Dashboard theme tokens
        blackBg: '#1e1e2f',
        blackCard: '#27293d',
        blackCardHover: '#2e3148',
        blackBorder: 'rgba(255, 255, 255, 0.08)',
        blackPrimary: '#e14eca',
        blackSecondary: '#ba54f5',
        blackInfo: '#1d8cf8',
        blackSuccess: '#00f2c3',
        blackWarning: '#ff8d72',
        blackDanger: '#fd5d93',
        // backward compatibility tokens
        obsidian: '#1e1e2f',
        panel: '#27293d',
        panelLight: '#2e3148',
      },
      boxShadow: {
        'black-card': '0 1px 20px 0px rgba(0, 0, 0, 0.25)',
        'black-glow-pink': '0 0 20px rgba(225, 78, 202, 0.35)',
        'black-glow-blue': '0 0 20px rgba(29, 140, 248, 0.35)',
        'black-glow-green': '0 0 20px rgba(0, 242, 195, 0.35)',
      },
      backgroundImage: {
        'pink-gradient': 'linear-gradient(to bottom left, #e14eca, #ba54f5, #e14eca)',
        'blue-gradient': 'linear-gradient(to bottom left, #1d8cf8, #3358f4, #1d8cf8)',
        'green-gradient': 'linear-gradient(to bottom left, #00f2c3, #0098f0, #00f2c3)',
        'sidebar-gradient': 'linear-gradient(0deg, #ba54f5 0%, #e14eca 100%)',
      },
    },
  },
  plugins: [],
};
