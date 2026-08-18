import { Skeleton } from '@/components/Skeleton';

export default function RootLoading() {
  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8 space-y-4">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="aspect-video rounded-xl" />
        ))}
      </div>
    </div>
  );
}
