'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { clsx } from 'clsx';
import { useDebounce } from '@/lib/hooks';
import { fetcher, vehiclesUrl } from '@/lib/api';
import type { Vehicle, APIResponse } from '@/types';

interface Props {
  onSelect?: (vehicle: Vehicle) => void;
  placeholder?: string;
  className?: string;
}

interface VehicleListData {
  // data field from API envelope — array of vehicles
  0: Vehicle[];
}

export function PlateSearch({ onSelect, placeholder = 'Search plate…', className }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounced = useDebounce(query, 280);

  const { data: vehicles } = useSWR<Vehicle[]>(
    debounced.length >= 2 ? vehiclesUrl({ plate: debounced, limit: 8 }) : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  function handleSelect(v: Vehicle) {
    setQuery(v.plate_number);
    setOpen(false);
    if (onSelect) {
      onSelect(v);
    } else {
      router.push(`/vehicles/${v.id}`);
    }
  }

  const showDropdown = open && debounced.length >= 2;

  return (
    <div ref={containerRef} className={clsx('relative', className)}>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-500">
          ⌕
        </span>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value.toUpperCase());
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2 pl-8 pr-4 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600/30"
          autoComplete="off"
          spellCheck={false}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false); }}
            className="absolute inset-y-0 right-2 flex items-center px-1 text-gray-500 hover:text-gray-300"
          >
            ✕
          </button>
        )}
      </div>

      {showDropdown && vehicles !== undefined && (
        <ul className="absolute z-50 mt-1 w-full overflow-hidden rounded-lg border border-gray-700 bg-gray-900 shadow-xl animate-fade-in">
          {vehicles.length === 0 ? (
            <li className="px-4 py-3 text-sm text-gray-500">No vehicles found</li>
          ) : (
            vehicles.map((v) => (
              <li key={v.id}>
                <button
                  onClick={() => handleSelect(v)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-gray-800"
                >
                  <span className="font-mono font-semibold text-gray-100">
                    {v.plate_number}
                  </span>
                  <span className="text-xs text-gray-500">
                    {v.total_scans} scan{v.total_scans !== 1 ? 's' : ''}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
