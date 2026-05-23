import { useEffect, useState } from 'react'
import Photo from './Photo'
import { ATELIER } from './theme'

interface Props {
  tone?: 'warm' | 'sand' | 'cream' | 'mauve' | 'blush'
}

// Self-running animation: selfie tile + scan reticle, then a grid of matched
// photos fades in one by one, then resets.
export default function MagicScan({ tone = 'sand' }: Props) {
  const t = ATELIER
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

  const matched: { tone: 'warm' | 'sand' | 'cream' | 'mauve' | 'blush' }[] = [
    { tone: 'sand' },
    { tone: 'cream' },
    { tone: 'warm' },
    { tone: 'mauve' },
    { tone: 'sand' },
    { tone: 'blush' },
    { tone: 'warm' },
    { tone: 'cream' },
  ]

  return (
    <div
      className="grid items-center gap-10 md:gap-14"
      style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}
    >
      <style>{`
        @media (min-width: 768px) {
          .atelier-magic-grid {
            grid-template-columns: 280px 1fr !important;
          }
        }
      `}</style>
      <div className="atelier-magic-grid grid items-center gap-10 md:gap-14" style={{ gridTemplateColumns: '1fr' }}>
        {/* selfie panel */}
        <div style={{ position: 'relative', maxWidth: 320, marginInline: 'auto', width: '100%' }}>
          <div
            style={{
              position: 'relative',
              aspectRatio: '3/4',
              border: `1px solid ${t.muted}55`,
              padding: 14,
              background: t.paper,
            }}
          >
            <Photo tone={tone} aspect="3/4" />
            {/* scan reticle */}
            <div
              style={{
                position: 'absolute',
                inset: 14,
                pointerEvents: 'none',
              }}
            >
              {/* corner brackets */}
              <div style={{ position: 'absolute', top: 16, left: 16, width: 22, height: 22, borderTop: `2px solid ${t.accent}`, borderLeft: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', top: 16, right: 16, width: 22, height: 22, borderTop: `2px solid ${t.accent}`, borderRight: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', bottom: 16, left: 16, width: 22, height: 22, borderBottom: `2px solid ${t.accent}`, borderLeft: `2px solid ${t.accent}` }} />
              <div style={{ position: 'absolute', bottom: 16, right: 16, width: 22, height: 22, borderBottom: `2px solid ${t.accent}`, borderRight: `2px solid ${t.accent}` }} />
              {/* scan line */}
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
              letterSpacing: '0.14em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            01 · guest selfie
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
              letterSpacing: '0.14em',
              color: t.muted,
              textTransform: 'uppercase',
            }}
          >
            02 · your photos · 2.4s
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
