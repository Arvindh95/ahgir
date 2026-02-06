export function SkeletonBox({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-white/10 rounded ${className}`} />
}

export function SkeletonText({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-white/10 rounded h-4 ${className}`} />
}
