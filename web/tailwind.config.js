export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        shell: '#0a0a0a',
        panel: '#111111',
        panel2: '#1a1a1a',
        border: '#2a2a2a',
        text: '#e8e0d8',
        dim: '#8a7e72',
        accent: '#ff6b00',
        'accent-light': '#ff8c33',
        'accent-dim': '#cc5500',
        neon: '#ff6b00',
        cyan: '#ff6b00',
        blue: '#6ba3ff',
        amber: '#ffb84d',
        danger: '#ff4d4d',
        safe: '#4dff88',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
