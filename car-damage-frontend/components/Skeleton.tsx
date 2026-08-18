'use client';

import { clsx } from 'clsx';

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={clsx(
        'animate-pulse rounded-md bg-gray-800',
        className
      )}
    />
  );
}

export function CameraCardSkeleton() {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-8" />
      </div>
      <Skeleton className="aspect-video w-full rounded-none" />
      <div className="px-3 py-2">
        <Skeleton className="h-4 w-28" />
      </div>
    </div>
  );
}

export function VehicleRowSkeleton() {
  return (
    <tr>
      {Array.from({ length: 6 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

export function ScanCardSkeleton() {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <Skeleton className="h-3 w-3 rounded-full" />
        <Skeleton className="w-0.5 h-16 mt-1" />
      </div>
      <div className="flex-1 pb-6">
        <Skeleton className="h-5 w-40 mb-2" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  );
}

export function ScanDetailSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex gap-3 overflow-hidden">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-64 flex-shrink-0 rounded-lg" />
        ))}
      </div>
      <div className="rounded-xl border border-gray-800">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-4 px-4 py-3 border-b border-gray-800 last:border-0"
          >
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function PageHeaderSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-72" />
    </div>
  );
}
