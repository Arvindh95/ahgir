import { CSSProperties, useState } from 'react'

type Tone = 'warm' | 'sand' | 'cream' | 'mauve' | 'sage' | 'dusk' | 'ink' | 'blush'

interface Props {
  tone?: Tone
  label?: string
  aspect?: string
  src?: string
  alt?: string
  style?: CSSProperties
}

// Portrait placeholder. Falls back to abstract gradient if `src` 404s.
const palettes: Record<Tone, [string, string, string]> = {
  warm:  ['#48352a', '#3b2a21', '#251a14'],
  sand:  ['#4a3a2a', '#3a2c1f', '#241a10'],
  cream: ['#3a3024', '#2c2418', '#1a140c'],
  mauve: ['#3e2c30', '#2e2024', '#1d141a'],
  sage:  ['#2f3328', '#23271d', '#161a10'],
  dusk:  ['#3a2f28', '#241d18', '#15100c'],
  ink:   ['#2a2521', '#221d1a', '#181513'],
  blush: ['#3d2a26', '#2c1d19', '#1a100d'],
}

export default function Photo({
  tone = 'dusk',
  label,
  aspect = '3/4',
  src,
  alt = '',
  style,
}: Props) {
  const [c1, c2, c3] = palettes[tone] || palettes.dusk
  const [imgFailed, setImgFailed] = useState(false)
  const showImg = src && !imgFailed
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: aspect,
        borderRadius: 2,
        overflow: 'hidden',
        background: `linear-gradient(135deg, ${c1} 0%, ${c2} 60%, ${c3} 100%)`,
        ...style,
      }}
    >
      {showImg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt}
          onError={() => setImgFailed(true)}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      ) : (
        <>
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,.03) 0 2px, transparent 2px 5px)`,
              mixBlendMode: 'overlay',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: '38%',
              transform: 'translateX(-50%)',
              width: '36%',
              aspectRatio: '1',
              borderRadius: '50%',
              background: `radial-gradient(circle at 50% 45%, ${c1} 0%, ${c1} 38%, transparent 70%)`,
              opacity: 0.45,
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '50%',
              top: '72%',
              transform: 'translateX(-50%)',
              width: '70%',
              height: '40%',
              borderRadius: '50% 50% 0 0 / 100% 100% 0 0',
              background: c1,
              opacity: 0.45,
            }}
          />
        </>
      )}
      {label && (
        <div
          style={{
            position: 'absolute',
            left: 10,
            bottom: 8,
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'rgba(212,165,116,.85)',
            textShadow: '0 1px 2px rgba(0,0,0,.5)',
          }}
        >
          {label}
        </div>
      )}
    </div>
  )
}
