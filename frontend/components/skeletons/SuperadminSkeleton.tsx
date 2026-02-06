import { SkeletonBox, SkeletonText } from './Skeleton'

export default function SuperadminSkeleton() {
  return (
    <div className="max-w-7xl mx-auto">
      {/* Title */}
      <SkeletonText className="w-64 h-8 mb-8" />

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="glass-card p-4 rounded-xl text-center">
            <SkeletonText className="w-16 h-7 mx-auto mb-2" />
            <SkeletonText className="w-12 h-3 mx-auto" />
          </div>
        ))}
      </div>

      {/* User table */}
      <div className="glass-card p-6 rounded-2xl">
        <SkeletonText className="w-48 h-6 mb-6" />
        <div className="space-y-0">
          {/* Header row */}
          <div className="flex items-center gap-4 pb-3 border-b border-white/10">
            <SkeletonText className="flex-1" />
            <SkeletonText className="w-16" />
            <SkeletonText className="w-20" />
            <SkeletonText className="w-24" />
            <SkeletonText className="w-20" />
          </div>
          {/* Data rows */}
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="flex items-center gap-4 py-3 border-b border-white/5">
              <SkeletonText className="flex-1" />
              <SkeletonText className="w-16" />
              <SkeletonBox className="w-20 h-5 rounded" />
              <SkeletonText className="w-24" />
              <div className="flex gap-2 w-20 justify-end">
                <SkeletonBox className="w-7 h-7 rounded-lg" />
                <SkeletonBox className="w-7 h-7 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
