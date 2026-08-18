'use client';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <span className="text-5xl">⚠</span>
      <h2 className="text-xl font-semibold text-gray-100">
        Something went wrong
      </h2>
      <p className="max-w-md text-sm text-gray-500">{error.message}</p>
      <button
        onClick={reset}
        className="mt-2 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
      >
        Try again
      </button>
    </div>
  );
}
