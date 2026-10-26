/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: "#050811",
          canvas: "#03060C",
          panel: "rgba(8, 14, 25, 0.85)",
          panelSolid: "#080F1D",
          border: "rgba(0, 240, 255, 0.25)",
          borderSubtle: "rgba(0, 240, 255, 0.12)",
          borderActive: "#00F0FF",
          cyan: "#00F0FF",
          cyanMuted: "#0284C7",
          green: "#00FF88",
          red: "#FF2B44",
          redDark: "#880E1E",
          blue: "#38BDF8",
          purple: "#A855F7",
          amber: "#F59E0B",
          text: "#F8FAFC",
          textMuted: "#64748B",
          textDim: "#334155"
        }
      },
      fontFamily: {
        mono: ['"Share Tech Mono"', 'Consolas', 'monospace'],
        hud: ['"Rajdhani"', 'Inter', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif']
      },
      boxShadow: {
        'hud-cyan': '0 0 15px rgba(0, 240, 255, 0.3)',
        'hud-cyan-lg': '0 0 25px rgba(0, 240, 255, 0.45)',
        'hud-green': '0 0 15px rgba(0, 255, 136, 0.35)',
        'hud-red': '0 0 20px rgba(255, 43, 68, 0.4)',
        'hud-red-lg': '0 0 35px rgba(255, 43, 68, 0.6)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'trace-flow': 'traceFlow 2s linear infinite',
        'scanline': 'scanline 8s linear infinite',
      },
      keyframes: {
        traceFlow: {
          '0%': { strokeDashoffset: '100' },
          '100%': { strokeDashoffset: '0' },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(1000%)' }
        }
      }
    },
  },
  plugins: [],
}
