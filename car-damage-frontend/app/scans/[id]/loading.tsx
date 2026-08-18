import { Skeleton, ScanDetailSkeleton } from '@/components/Skeleton';

export default function ScanDetailLoading() {
  return (
    <div className="mx-auto max-w-[1300px] px-6 py-8 space-y-6">
      <Skeleton className="h-3 w-56" />
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-44" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-36 rounded-lg" />
      </div>
      <ScanDetailSkeleton />
    </div>
  );
}
