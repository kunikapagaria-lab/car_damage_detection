'use client';

import { useRouter } from 'next/navigation';

export default function ScanDetailError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-[1300px] px-6 py-16 text-center">
      <p className="text-sm text-red-400">{error.message}</p>
      <div className="mt-4 flex justify-center gap-3">
        <button
          onClick={reset}
          className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
        >
          Retry
        </button>
        <button
          onClick={() => router.back()}
          className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 hover:bg-gray-900"
        >
          Go back
        </button>
      </div>
    </div>
  );
}
