import type { GetServerSideProps } from 'next'

const SITE = 'https://picur.my'

// Public pages worth indexing. Admin / guest event pages are intentionally
// excluded — they're either authenticated or per-event ephemeral.
const STATIC_PATHS: Array<{ path: string; changefreq: string; priority: string }> = [
  { path: '/', changefreq: 'weekly', priority: '1.0' },
  { path: '/pricing', changefreq: 'weekly', priority: '0.9' },
  { path: '/contact', changefreq: 'monthly', priority: '0.7' },
  { path: '/privacy', changefreq: 'yearly', priority: '0.3' },
  { path: '/terms', changefreq: 'yearly', priority: '0.3' },
]

function buildSitemap(): string {
  const lastmod = new Date().toISOString().split('T')[0]
  const urls = STATIC_PATHS.map(
    ({ path, changefreq, priority }) => `
  <url>
    <loc>${SITE}${path}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>${changefreq}</changefreq>
    <priority>${priority}</priority>
  </url>`,
  ).join('')

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}
</urlset>`
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const xml = buildSitemap()
  res.setHeader('Content-Type', 'application/xml; charset=utf-8')
  res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=3600')
  res.write(xml)
  res.end()
  return { props: {} }
}

// Rendered output is unused — getServerSideProps writes the response directly.
export default function Sitemap() {
  return null
}
