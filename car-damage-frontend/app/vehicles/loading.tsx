import { Skeleton, VehicleRowSkeleton } from '@/components/Skeleton';

export default function VehiclesLoading() {
  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <div className="mb-6 flex items-end justify-between">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-9 w-72 rounded-lg" />
      </div>
      <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900">
        <table className="w-full">
          <tbody>
            {Array.from({ length: 10 }).map((_, i) => (
              <VehicleRowSkeleton key={i} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
