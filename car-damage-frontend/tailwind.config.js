/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        scratch: { DEFAULT: '#EF4444', muted: 'rgba(239,68,68,0.18)' },
        dent: { DEFAULT: '#3B82F6', muted: 'rgba(59,130,246,0.18)' },
        paint_damage: { DEFAULT: '#EAB308', muted: 'rgba(234,179,8,0.18)' },
        crack: { DEFAULT: '#A855F7', muted: 'rgba(168,85,247,0.18)' },
      },
      animation: {
        'ticker': 'ticker 40s linear infinite',
        'pulse-once': 'pulse 0.6s ease-out 1',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        ticker: {
          '0%': { transform: 'translateX(0%)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(-4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
