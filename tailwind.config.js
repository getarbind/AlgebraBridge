/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Lexend', 'ui-sans-serif', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Representation colors are shared by the scale and the KaTeX equation
        // so the learner can map icon <-> symbol at a glance (dual coding).
        paper: '#f6f2e9',
        card: '#fffdf8',
        ink: { DEFAULT: '#1d2433', soft: '#4a5263', faint: '#7c8291' },
        rule: '#e4dccb',
        variable: { DEFAULT: '#5b3fd1', light: '#ece8fc', dark: '#3f2a9e' },
        unit: { DEFAULT: '#b07a12', light: '#fbf0d6', dark: '#7d560b' },
        negative: { DEFAULT: '#c8433a', light: '#fbe5e2' },
        balanced: { DEFAULT: '#1f8a5b', light: '#dff3e8' },
        tipped: { DEFAULT: '#c46a00', light: '#fdebd3' },
      },
      boxShadow: {
        block: 'inset 0 -3px 0 rgba(0,0,0,0.18)',
        card: '0 1px 0 #e4dccb, 0 8px 24px -12px rgba(29,36,51,0.18)',
      },
    },
  },
  plugins: [],
};
