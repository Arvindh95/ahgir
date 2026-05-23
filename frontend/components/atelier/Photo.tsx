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

// Falls back to the abstract gradient if the user-supplied image 404s.

const palettes: Record<Tone, [string, string, string]> = {
  warm:  ['#d9c8b4', '#c4ad93', '#b09376'],
  sand:  ['#e8dac6', '#d6c4ac', '#bfa98c'],
  cream: ['#efe6d4', '#dccbb1', '#c4b08e'],
  mauve: ['#d6c0c4', '#c0a4ab', '#a4858d'],
  sage:  ['#cdd2c0', '#b6bea7', '#9aa68a'],
  dusk:  ['#5a4e44', '#48403a', '#332d29'],
  ink:   ['#2a2521', '#221d1a', '#181513'],
  blush: ['#ecd4cf', '#d8b8b2', '#bf9a93'],
}

// Portrait placeholder. If `src` is provided, renders the real image with the
// same paper-bordered framing. Otherwise renders an abstract striped silhouette.
export default function Photo({
  tone = 'warm',
  label,
  aspect = '3/4',
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
              backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,.04) 0 2px, transparent 2px 5px)`,
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
              background: `radial-gradient(circle at 50% 45%, ${c3} 0%, ${c3} 38%, transparent 70%)`,
              opacity: 0.55,
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
              background: c3,
              opacity: 0.55,
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
