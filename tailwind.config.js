/** Tailwind v3 — admin panel uchun statik CSS build.
 *  Qayta qurish:  npm run css   (yoki  npm run css:watch)
 *  Chiqish fayli: app/admin/static/app.css  ->  base.html unga <link> qiladi.
 */
module.exports = {
  darkMode: 'class',  // html.dark klassi bo'yicha tungi rejim
  content: ['./app/admin/templates/**/*.html'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'] },
      colors: {
        brand: {
          50: '#eef4ff', 100: '#dbe7fe', 200: '#bfd3fe', 300: '#93b4fb', 400: '#5b8def',
          500: '#2563eb', 600: '#1d4ed8', 700: '#1e40af', 800: '#1b3576', 900: '#0f1e3d', 950: '#0a1530',
        },
        ink: {
          900: '#0f172a', 800: '#1e293b', 700: '#334155', 600: '#475569',
          500: '#64748b', 400: '#94a3b8', 300: '#cbd5e1',
        },
      },
    },
  },
  /* JS ichida dinamik yasaladigan (ehtimoliy) klasslar — har doim kiritilsin */
  safelist: [
    'bg-brand-600', 'bg-violet-600', 'bg-violet-500',
    'text-amber-400', 'text-emerald-400', 'text-rose-500',
    'justify-end', 'justify-start',
  ],
  plugins: [],
}
