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

// Falls back to the abstract gradient if the user-supplied image 404s.

const palettes: Record<Tone, [string, string, string]> = {
  warm:  ['#d9c8b4', '#b09376', '#7a5e44'],
  sand:  ['#e6d4b8', '#c4a576', '#8a6a44'],
  dusk:  ['#5a4e44', '#3a3530', '#1a1612'],
  cream: ['#efe6d4', '#cdb88e', '#7c5e3a'],
  mauve: ['#d6c0c4', '#a4858d', '#5e4348'],
  blush: ['#f2dad3', '#c89f96', '#7a4d49'],
  ink:   ['#3a3230', '#2a2521', '#181513'],
}

// Landscape scene placeholder (couples, ceremony, dance). Optional `src`
// swaps in a real image with the same framing.
export default function Scene({
  tone = 'warm',
  label,
  aspect = '3/2',
  src,
  alt = '',
  style,
}: Props) {
  const [c1, c2, c3] = palettes[tone] || palettes.warm
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
              backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,.05) 0 2px, transparent 2px 6px)`,
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
              background: `linear-gradient(180deg, transparent, ${c3} 60%)`,
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
              background: c3,
              opacity: 0.6,
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
              background: c3,
              opacity: 0.6,
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
            color: 'rgba(255,255,255,.85)',
            textShadow: '0 1px 2px rgba(0,0,0,.3)',
          }}
        >
          {label}
        </div>
      )}
    </div>
  )
}
