import { ATELIER } from './theme'

interface TickerItem {
  name: string
  where: string
  count: number
  guests: number
}

interface Props {
  items?: TickerItem[]
  title?: string
}

const DEFAULTS: TickerItem[] = [
  { name: 'Maria & David', where: 'Bali, ID', count: 247, guests: 412 },
  { name: 'Kenji × Aiko', where: 'Kyoto, JP', count: 1042, guests: 180 },
  { name: 'The Patel Family', where: 'Jaipur, IN', count: 3318, guests: 740 },
  { name: 'Lucia & Tom', where: 'Tuscany, IT', count: 188, guests: 95 },
  { name: 'Sade & Femi', where: 'Lagos, NG', count: 2247, guests: 600 },
  { name: 'Emma & Charlie', where: 'Cotswolds, UK', count: 462, guests: 220 },
  { name: 'Noor & Yusuf', where: 'Marrakech, MA', count: 894, guests: 320 },
  { name: 'River & Sage', where: 'Big Sur, US', count: 312, guests: 80 },
]

// Vertically scrolling marquee of recent events. Pure CSS animation, no JS.
export default function Ticker({ items, title = 'LIVE NOW' }: Props) {
  const list = items || DEFAULTS
  const loop = [...list, ...list]
  const dur = list.length * 3.2
  const t = ATELIER

  return (
    <div
      style={{
        position: 'relative',
        borderTop: `1px solid ${t.muted}33`,
        borderBottom: `1px solid ${t.muted}33`,
        padding: '18px 0',
        overflow: 'hidden',
        background: t.paper,
      }}
    >
      {/* edge fades */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: 60,
          background: `linear-gradient(90deg, ${t.paper} 0%, transparent 100%)`,
          zIndex: 2,
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          right: 0,
          width: 60,
          background: `linear-gradient(270deg, ${t.paper} 0%, transparent 100%)`,
          zIndex: 2,
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 36,
          padding: '0 28px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flex: '0 0 auto',
            fontFamily: t.monoFont,
            fontSize: 10,
            letterSpacing: '0.18em',
            color: t.ink,
            textTransform: 'uppercase',
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: t.accent,
              boxShadow: `0 0 0 4px ${t.accent}33`,
              animation: 'atelier-pulse 1.4s infinite',
            }}
          />
          {title}
        </div>
        <div style={{ flex: 1, overflow: 'hidden', height: 22, position: 'relative' }}>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              animation: `atelier-marquee ${dur}s linear infinite`,
            }}
          >
            {loop.map((e, i) => (
              <div
                key={i}
                style={{
                  height: 22,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  fontFamily: t.displayFont,
                  fontStyle: 'italic',
                  fontSize: 18,
                  color: t.ink,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ fontStyle: 'italic' }}>{e.name}</span>
                <span
                  style={{
                    fontFamily: t.monoFont,
                    fontStyle: 'normal',
                    fontSize: 10,
                    letterSpacing: '0.08em',
                    color: t.muted,
                    textTransform: 'uppercase',
                  }}
                >
                  {e.where}
                </span>
                <span
                  style={{
                    fontFamily: t.monoFont,
                    fontStyle: 'normal',
                    fontSize: 10,
                    letterSpacing: '0.08em',
                    color: t.muted,
                  }}
                >
                  · {e.count} photos · {e.guests} guests
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
