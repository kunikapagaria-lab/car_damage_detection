import { Skeleton } from '@/components/Skeleton';

export default function AlertsLoading() {
  return (
    <div className="mx-auto max-w-[900px] px-6 py-8 space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-14 w-full rounded-xl" />
      <div className="space-y-2 mt-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
