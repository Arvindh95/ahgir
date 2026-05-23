import { LUMIERE } from './theme'

interface Props {
  // Distance from each edge of the parent container.
  inset?: number
  // Size of each mark in px.
  size?: number
  // Opacity multiplier on top of the base accent color.
  opacity?: number
  // Stroke color override.
  color?: string
}

// Film-frame corner ticks. Parent must be `position: relative` (or anything
// non-static). All four corners drawn from inside the inset rectangle.
export default function CornerMarks({
  inset = 32,
  size = 16,
  opacity = 0.4,
  color,
}: Props) {
  const stroke = color || `${LUMIERE.accent}${Math.round(opacity * 255).toString(16).padStart(2, '0')}`
  const lineWidth = 1
  const lineStyle = `${lineWidth}px solid ${stroke}`

  return (
    <div
      aria-hidden
      style={{
        position: 'absolute',
        top: inset,
        right: inset,
        bottom: inset,
        left: inset,
        pointerEvents: 'none',
      }}
    >
      <div style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, borderTop: lineStyle, borderLeft: lineStyle }} />
      <div style={{ position: 'absolute', top: 0, right: 0, width: size, height: size, borderTop: lineStyle, borderRight: lineStyle }} />
      <div style={{ position: 'absolute', bottom: 0, left: 0, width: size, height: size, borderBottom: lineStyle, borderLeft: lineStyle }} />
      <div style={{ position: 'absolute', bottom: 0, right: 0, width: size, height: size, borderBottom: lineStyle, borderRight: lineStyle }} />
    </div>
  )
}
