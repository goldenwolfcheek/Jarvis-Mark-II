/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: '#050810',
          surface: '#0d1520',
          panel: 'rgba(13, 21, 32, 0.85)',
          accent: '#00d4ff',
          accent2: '#0088cc',
          text: '#e0e8f0',
          muted: '#6b7c93',
          border: 'rgba(255, 255, 255, 0.08)',
          success: '#00e676',
          warning: '#ffab00',
          error: '#ff5252',
        },
      },
      fontFamily: {
        mono: ['"Cascadia Code"', '"Fira Code"', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      backdropBlur: {
        glass: '24px',
      },
      animation: {
        'spin-slow': 'spin 8s linear infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'typing': 'typing 1.4s infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { opacity: '0.6' },
          '50%': { opacity: '1' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideIn: {
          from: { transform: 'translateX(100%)' },
          to: { transform: 'translateX(0)' },
        },
        typing: {
          '0%, 60%, 100%': { opacity: '0.3' },
          '30%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
