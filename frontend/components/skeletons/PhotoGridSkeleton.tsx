import { SkeletonBox, SkeletonText } from './Skeleton'

interface PhotoGridSkeletonProps {
  count?: number
  columns?: string
}

export default function PhotoGridSkeleton({
  count = 12,
  columns = 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
}: PhotoGridSkeletonProps) {
  return (
    <div className={`grid ${columns} gap-6`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="glass-card rounded-2xl overflow-hidden">
          <SkeletonBox className="aspect-[4/3] rounded-none" />
          <div className="p-4 flex gap-3">
            <SkeletonBox className="flex-1 h-8 rounded-lg" />
            <SkeletonBox className="flex-1 h-8 rounded-lg" />
            <SkeletonBox className="flex-1 h-8 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}
