import { useEffect, useState } from 'react'
import Photo from './Photo'
import Scene from './Scene'
import { ATELIER } from './theme'

interface Props {
  tone?: 'warm' | 'sand' | 'cream' | 'mauve' | 'blush'
  scale?: number
}

// Stylized iPhone-shaped frame cycling through three guest screens:
// 01 event landing → 02 selfie scan → 03 matched gallery
export default function PhoneFlow({ tone = 'sand', scale = 1 }: Props) {
  const t = ATELIER
  const [screen, setScreen] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setScreen((s) => (s + 1) % 3), 2600)
    return () => clearInterval(id)
  }, [])

  const W = 280 * scale
  const H = 580 * scale

  return (
    <div
      style={{
        width: W,
        height: H,
        borderRadius: 38 * scale,
        background: '#0d0c0a',
        padding: 8 * scale,
        boxShadow: `0 30px 80px ${t.ink}22, 0 0 0 1px ${t.ink}11`,
        position: 'relative',
      }}
    >
      {/* notch */}
      <div
        style={{
          position: 'absolute',
          top: 16 * scale,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 78 * scale,
          height: 22 * scale,
          borderRadius: 14 * scale,
          background: '#0d0c0a',
          zIndex: 3,
        }}
      />
      <div
        style={{
          width: '100%',
          height: '100%',
          borderRadius: 30 * scale,
          overflow: 'hidden',
          background: t.paper,
          position: 'relative',
        }}
      >
        {/* status bar */}
        <div
          style={{
            height: 38 * scale,
            padding: `0 ${22 * scale}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: t.bodyFont,
            fontSize: 12 * scale,
            fontWeight: 600,
            color: t.ink,
          }}
        >
          <span>9:41</span>
          <span
            style={{
              display: 'inline-block',
              width: 24 * scale,
              height: 12 * scale,
              background: t.ink,
              borderRadius: 2,
              opacity: 0.7,
            }}
          />
        </div>

        <div style={{ position: 'relative', height: `calc(100% - ${38 * scale}px)` }}>
          {/* Screen 0: event landing */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              opacity: screen === 0 ? 1 : 0,
              transition: 'opacity .5s',
              padding: 20 * scale,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={{ flex: 1, position: 'relative' }}>
              <Scene tone={tone} aspect="3/4" />
            </div>
            <div
              style={{
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 28 * scale,
                lineHeight: 1.05,
                color: t.ink,
                marginTop: 14 * scale,
              }}
            >
              Maria
              <br />& David
            </div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 9 * scale,
                letterSpacing: '0.14em',
                color: t.muted,
                textTransform: 'uppercase',
                marginTop: 6 * scale,
              }}
            >
              BALI · MAY 24
            </div>
            <div
              style={{
                marginTop: 14 * scale,
                padding: `${12 * scale}px ${16 * scale}px`,
                borderRadius: 999,
                background: t.ink,
                color: t.paper,
                textAlign: 'center',
                fontFamily: t.bodyFont,
                fontWeight: 600,
                fontSize: 13 * scale,
              }}
            >
              Find my photos →
            </div>
          </div>

          {/* Screen 1: selfie scan */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              opacity: screen === 1 ? 1 : 0,
              transition: 'opacity .5s',
              padding: 20 * scale,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              style={{
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 22 * scale,
                color: t.ink,
              }}
            >
              look at me
            </div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 9 * scale,
                color: t.muted,
                letterSpacing: '0.1em',
                marginTop: 4 * scale,
                textTransform: 'uppercase',
              }}
            >
              WE&apos;LL FIND YOU IN SECONDS
            </div>
            <div style={{ flex: 1, marginTop: 14 * scale, position: 'relative' }}>
              <Photo tone={tone} aspect="3/4" />
              <div
                style={{
                  position: 'absolute',
                  inset: '12% 22%',
                  border: `1.5px solid ${t.accent}`,
                  borderRadius: '50%',
                  animation: 'atelier-pulse 1.6s infinite',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  left: 14 * scale,
                  right: 14 * scale,
                  top: '50%',
                  height: 1,
                  background: t.accent,
                  opacity: 0.9,
                  boxShadow: `0 0 10px ${t.accent}`,
                }}
              />
            </div>
            <div
              style={{
                marginTop: 14 * scale,
                textAlign: 'center',
                fontFamily: t.monoFont,
                fontSize: 10 * scale,
                color: t.muted,
                letterSpacing: '0.12em',
              }}
            >
              SCANNING…
            </div>
          </div>

          {/* Screen 2: matched gallery */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              opacity: screen === 2 ? 1 : 0,
              transition: 'opacity .5s',
              padding: 20 * scale,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              style={{
                fontFamily: t.displayFont,
                fontStyle: 'italic',
                fontSize: 26 * scale,
                color: t.ink,
              }}
            >
              you, found.
            </div>
            <div
              style={{
                fontFamily: t.monoFont,
                fontSize: 9 * scale,
                color: t.muted,
                letterSpacing: '0.1em',
                marginTop: 4 * scale,
                textTransform: 'uppercase',
              }}
            >
              23 PHOTOS · TAP TO DOWNLOAD
            </div>
            <div
              style={{
                flex: 1,
                marginTop: 14 * scale,
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 6 * scale,
                gridAutoRows: '1fr',
              }}
            >
              {(['sand', 'warm', 'cream', 'mauve', 'sand', 'blush'] as const).map((tn, i) => (
                <Photo key={i} tone={tn} aspect="3/4" />
              ))}
            </div>
          </div>
        </div>
        {/* home indicator */}
        <div
          style={{
            position: 'absolute',
            bottom: 8 * scale,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 100 * scale,
            height: 4 * scale,
            borderRadius: 4,
            background: t.ink,
            opacity: 0.6,
          }}
        />
      </div>
    </div>
  )
}
