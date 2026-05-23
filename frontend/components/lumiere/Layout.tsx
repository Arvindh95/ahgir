import Nav from './Nav'
import Footer from './Footer'
import { LUMIERE } from './theme'

interface Props {
  children: React.ReactNode
  // Pages with a bespoke top (e.g. guest event landing) skip the shared
  // nav/footer while still inheriting the .lumiere theme wrapper.
  bare?: boolean
}

export default function Layout({ children, bare = false }: Props) {
  return (
    <div
      className="lumiere"
      style={{
        background: LUMIERE.bg,
        color: LUMIERE.ink,
        fontFamily: LUMIERE.bodyFont,
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
