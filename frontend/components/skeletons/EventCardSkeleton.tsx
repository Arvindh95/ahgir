import { SkeletonBox, SkeletonText } from './Skeleton'

function EventCardSkeleton() {
  return (
    <div className="glass-card p-6 rounded-2xl">
      <div className="flex justify-between items-start mb-4">
        <SkeletonText className="w-2/3 h-6" />
        <SkeletonBox className="w-5 h-5" />
      </div>
      <div className="space-y-2 mb-6">
        <SkeletonText className="w-1/2" />
        <SkeletonBox className="w-20 h-5 rounded" />
      </div>
      <div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-4 mt-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="text-center">
            <SkeletonText className="w-12 mx-auto mb-1 h-3" />
            <SkeletonText className="w-8 mx-auto h-5" />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function EventCardSkeletonGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {[1, 2, 3, 4, 5, 6].map(i => (
        <EventCardSkeleton key={i} />
      ))}
    </div>
  )
}
