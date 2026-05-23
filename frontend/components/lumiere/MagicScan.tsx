import { useEffect, useState } from 'react'
import Photo from './Photo'
import { LUMIERE } from './theme'

interface Props {
  tone?: 'warm' | 'sand' | 'cream' | 'mauve' | 'blush' | 'dusk'
}

// Self-running animation: selfie tile + scan reticle, then matched photo grid.
export default function MagicScan({ tone = 'dusk' }: Props) {
  const t = LUMIERE
  const [stage, setStage] = useState(0)

  useEffect(() => {
    const ids: ReturnType<typeof setTimeout>[] = []
    const cycle = () => {
      ids.push(setTimeout(() => setStage(1), 1200))
      ids.push(setTimeout(() => setStage(2), 2400))
      ids.push(setTimeout(() => setStage(3), 3600))
      ids.push(setTimeout(() => setStage(0), 5400))
    }
    cycle()
    const interval = setInterval(cycle, 5400)
    return () => {
      ids.forEach(clearTimeout)
      clearInterval(interval)
    }
  }, [])

  const matched: { tone: 'warm' | 'sand' | 'cream' | 'mauve' | 'blush' | 'dusk' }[] = [
    { tone: 'dusk' },
    { tone: 'cream' },
    { tone: 'warm' },
    { tone: 'mauve' },
    { tone: 'sand' },
    { tone: 'blush' },
    { tone: 'warm' },
    { tone: 'dusk' },
  ]

  return (
    <div>
      <style>{`
        .lumiere-magic-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 40px;
          align-items: center;
        }
        @media (min-width: 768px) {
          .lumiere-magic-grid {
            grid-template-columns: 280px 1fr;
            gap: 56px;
          }
        }
      `}</style>
      <div className="lumiere-magic-grid">
        {/* selfie panel */}
        <div style={{ position: 'relative', maxWidth: 320, marginInline: 'auto', width: '100%' }}>
          <div
            style={{
              position: 'relative',
              aspectRatio: '3/4',
              border: `1px solid ${t.border}`,
              padding: 14,
              background: t.bg,
            }}
          >
            <Photo tone={tone} aspect="3/4" />
            <div
              style={{
                position: 'absolute',
                inset: 14,
                pointerEvents: 'none',
              }}
            >
              <div style={{ position: 'absolute', top: 16, left: 16, width: 22, height: 22, borderTop: `2px solid ${t.accent}`, borderLeft: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', top: 16, right: 16, width: 22, height: 22, borderTop: `2px solid ${t.accent}`, borderRight: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', bottom: 16, left: 16, width: 22, height: 22, borderBottom: `2px solid ${t.accent}`, borderLeft: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', bottom: 16, right: 16, width: 22, height: 22, borderBottom: `2px solid ${t.accent}`, borderRight: `2px solid ${t.accent}` }} />
              <div
                style={{
                  position: 'absolute',
                  left: 16,
                  right: 16,
                  top: stage >= 1 ? '50%' : '15%',
                  height: 1,
                  background: t.accent,
                  boxShadow: `0 0 12px ${t.accent}`,
                  transition: 'top 1.1s cubic-bezier(.6,.05,.4,.95)',
                  opacity: stage === 0 ? 0 : stage === 3 ? 0 : 1,
                }}
              />
            </div>
          </div>
          <div
            style={{
              marginTop: 12,
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.18em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            01 · GUEST SELFIE
          </div>
          <div
            style={{
              marginTop: 4,
              fontFamily: t.displayFont,
              fontStyle: 'italic',
              fontSize: 22,
              color: t.ink,
              lineHeight: 1.1,
            }}
          >
            {stage === 0 && 'capturing…'}
            {stage === 1 && 'scanning…'}
            {stage === 2 && 'matching…'}
            {stage === 3 && '8 matches'}
          </div>
        </div>
        {/* matched photos */}
        <div style={{ position: 'relative' }}>
          <div
            style={{
              marginBottom: 14,
              fontFamily: t.monoFont,
              fontSize: 10,
              letterSpacing: '0.18em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            02 · THEIR PHOTOS · 2.4s
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 10,
            }}
          >
            {matched.map((m, i) => (
              <div
                key={i}
                style={{
                  opacity: stage >= 2 ? 1 : 0,
                  transform: stage >= 2 ? 'translateY(0)' : 'translateY(8px)',
                  transition: `opacity .4s ${i * 80}ms, transform .4s ${i * 80}ms`,
                }}
              >
                <Photo tone={m.tone} aspect="3/4" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
