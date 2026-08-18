import { Skeleton, ScanCardSkeleton, PageHeaderSkeleton } from '@/components/Skeleton';

export default function VehicleDetailLoading() {
  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8 space-y-6">
      <Skeleton className="h-3 w-40" />
      <PageHeaderSkeleton />
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-lg" />
        ))}
      </div>
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <ScanCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
