'use client';

export default function UploadError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-[1200px] px-6 py-16 text-center">
      <p className="text-sm text-red-400">{error.message}</p>
      <button
        onClick={reset}
        className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
      >
        Retry
      </button>
    </div>
  );
}
