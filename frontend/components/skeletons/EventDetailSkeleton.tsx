import { SkeletonBox, SkeletonText } from './Skeleton'

export default function EventDetailSkeleton() {
  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <SkeletonBox className="w-10 h-10 rounded-lg" />
        <SkeletonText className="w-48 h-8" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Left panel */}
        <div className="lg:col-span-2 glass-card p-6 rounded-2xl">
          <SkeletonText className="w-24 h-6 mb-6" />
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                <SkeletonText className="w-24" />
                <SkeletonText className="w-32" />
              </div>
            ))}
          </div>
        </div>

        {/* QR code panel */}
        <div className="glass-card p-6 rounded-2xl flex flex-col items-center">
          <SkeletonText className="w-24 h-6 mb-6" />
          <SkeletonBox className="w-56 h-56 rounded-xl" />
          <SkeletonText className="w-40 mt-4" />
        </div>
      </div>

      {/* Monitoring placeholder */}
      <div className="glass-card p-6 rounded-2xl mb-8">
        <SkeletonText className="w-48 h-6 mb-4" />
        <SkeletonBox className="w-full h-4 rounded-full mb-4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <SkeletonBox key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      </div>
    </div>
  )
}
