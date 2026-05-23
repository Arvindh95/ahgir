import { CSSProperties, useState } from 'react'

type Tone = 'warm' | 'sand' | 'dusk' | 'cream' | 'mauve' | 'blush' | 'ink'

interface Props {
  tone?: Tone
  label?: string
  aspect?: string
  src?: string
  alt?: string
  style?: CSSProperties
}

// Landscape placeholder (couples, ceremony). Falls back to gradient if src 404s.
const palettes: Record<Tone, [string, string, string]> = {
  warm:  ['#3a2c20', '#241a10', '#0e0a07'],
  sand:  ['#3e3022', '#241a0d', '#0e0a05'],
  dusk:  ['#382f28', '#1f1814', '#0c0907'],
  cream: ['#3c3120', '#241a0e', '#0e0a05'],
  mauve: ['#3a2a30', '#241820', '#0e070e'],
  blush: ['#3a221e', '#231510', '#0d0805'],
  ink:   ['#2a2520', '#1a1612', '#0a0807'],
}

export default function Scene({
  tone = 'dusk',
  label,
  aspect = '3/2',
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
        background: `linear-gradient(180deg, ${c1} 0%, ${c2} 45%, ${c3} 100%)`,
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
              backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,.04) 0 2px, transparent 2px 6px)`,
              mixBlendMode: 'overlay',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '15%',
              right: '15%',
              bottom: '12%',
              height: '34%',
              background: `linear-gradient(180deg, transparent, ${c1} 60%)`,
              borderRadius: '50% 50% 0 0',
              opacity: 0.55,
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '40%',
              bottom: '24%',
              width: '8%',
              aspectRatio: '1',
              borderRadius: '50%',
              background: c1,
              opacity: 0.5,
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '52%',
              bottom: '24%',
              width: '8%',
              aspectRatio: '1',
              borderRadius: '50%',
              background: c1,
              opacity: 0.5,
            }}
          />
        </>
      )}
      {label && (
        <div
          style={{
            position: 'absolute',
            left: 12,
            bottom: 10,
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
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
