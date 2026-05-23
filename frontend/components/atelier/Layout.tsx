import Nav from './Nav'
import Footer from './Footer'
import { ATELIER } from './theme'

interface Props {
  children: React.ReactNode
  // Pages with their own bespoke top (e.g. guest event landing) can hide the
  // shared nav/footer while still inheriting the .atelier theme wrapper.
  bare?: boolean
}

// Outer wrapper for all Atelier pages. Applies the cream paper background and
// the theme font on its descendants. Wrapping in .atelier scopes the override
// so existing dark pages (admin area) keep their original styling.
export default function Layout({ children, bare = false }: Props) {
  return (
    <div
      className="atelier"
      style={{
        background: ATELIER.bg,
        color: ATELIER.ink,
        fontFamily: ATELIER.bodyFont,
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {!bare && <Nav />}
      <main style={{ flex: 1 }}>{children}</main>
      {!bare && <Footer />}
    </div>
  )
}
