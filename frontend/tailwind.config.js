/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#070b14',
          900: '#0b0f19',
          850: '#0e1421',
          800: '#111827',
          700: '#1f2937',
          600: '#334155',
        },
        accent: {
          cyan: '#22d3ee',
          sky: '#06b6d4',
          blue: '#2563eb',
          deep: '#1d4ed8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'Geist', 'Segoe UI Variable', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['Geist Mono', 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(34,211,238,0.12), 0 12px 40px -12px rgba(6,182,212,0.28)',
        card: '0 20px 50px -32px rgba(0,0,0,0.85)',
        'card-hover': '0 24px 60px -28px rgba(0,0,0,0.9), 0 0 0 1px rgba(34,211,238,0.16)',
      },
      animation: {
        'pulse-soft': 'pulse-soft 2.6s ease-in-out infinite',
        'fade-up': 'fade-up 0.3s ease-out both',
        'slide-in': 'slide-in 0.28s cubic-bezier(0.22, 1, 0.36, 1) both',
        'scale-in': 'scale-in 0.2s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 2.8s linear infinite',
      },
      keyframes: {
        'pulse-soft': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.45', transform: 'scale(0.82)' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(28px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'translateY(10px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        shimmer: {
          from: { backgroundPosition: '200% 0' },
          to: { backgroundPosition: '-200% 0' },
        },
      },
    },
  },
  plugins: [],
};
