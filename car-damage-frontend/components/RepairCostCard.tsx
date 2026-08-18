'use client';

import { useMemo } from 'react';
import type { DamageClass } from '@/types';

export interface RepairCostCardProps {
  damages: Array<{
    class_name: string;
    confidence: number;
    mask_area_pct: number;
    mask_area_px?: number;
  }>;
  currencySymbol?: string;
}

const COST_RATES: Record<DamageClass, { baseCost: number; ratePerPct: number; label: string }> = {
  dent: { baseCost: 250, ratePerPct: 40, label: 'Dent & Body Panel Work' },
  scratch: { baseCost: 120, ratePerPct: 25, label: 'Clearcoat & Scratch Buffing' },
  paint_damage: { baseCost: 200, ratePerPct: 35, label: 'Paint Respray & Touch-up' },
  crack: { baseCost: 350, ratePerPct: 60, label: 'Structural Crack & Bumper Repair' },
};

export function RepairCostCard({ damages, currencySymbol = '$' }: RepairCostCardProps) {
  const breakdown = useMemo(() => {
    if (!damages || damages.length === 0) {
      return {
        totalCost: 0,
        severity: 'CLEAN',
        severityColor: 'bg-emerald-950 text-emerald-400 border-emerald-800',
        recommendation: 'No action required — vehicle passed body inspection.',
        items: [],
        totalAreaPct: 0,
      };
    }

    let totalCost = 0;
    let totalAreaPct = 0;

    const items = damages.map((d, index) => {
      const cls = (d.class_name as DamageClass) in COST_RATES ? (d.class_name as DamageClass) : 'scratch';
      const config = COST_RATES[cls];
      const areaPct = d.mask_area_pct || 1.5;
      const estimatedItemCost = Math.round(config.baseCost + areaPct * config.ratePerPct);

      totalCost += estimatedItemCost;
      totalAreaPct += areaPct;

      return {
        id: index,
        className: d.class_name,
        label: config.label,
        confidence: d.confidence,
        areaPct: areaPct.toFixed(2),
        cost: estimatedItemCost,
      };
    });

    let severity = 'MINOR';
    let severityColor = 'bg-amber-950 text-amber-400 border-amber-800';
    let recommendation = 'Minor cosmetic blemishes — schedule routine buffing.';

    if (totalCost > 500 || damages.length >= 3) {
      severity = 'CRITICAL';
      severityColor = 'bg-red-950 text-red-400 border-red-800 animate-pulse';
      recommendation = 'Major damage detected — immediate insurance claim recommended.';
    } else if (totalCost > 250 || damages.length >= 2) {
      severity = 'MODERATE';
      severityColor = 'bg-purple-950 text-purple-400 border-purple-800';
      recommendation = 'Panel damage detected — recommend body shop estimate.';
    }

    return {
      totalCost,
      severity,
      severityColor,
      recommendation,
      items,
      totalAreaPct: totalAreaPct.toFixed(2),
    };
  }, [damages]);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-4 mb-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
            <span>💳</span> Commercial Repair Cost & Claim Estimator
          </span>
          <h4 className="text-lg font-black text-gray-100 mt-0.5">
            Automated Damage Assessment
          </h4>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-md border px-2.5 py-1 text-xs font-black tracking-wide ${breakdown.severityColor}`}>
            SEVERITY: {breakdown.severity}
          </span>
        </div>
      </div>

      {breakdown.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <span className="text-4xl text-emerald-400 mb-2">✓</span>
          <p className="text-sm font-bold text-gray-200">Zero Repair Cost Estimated</p>
          <p className="text-xs text-gray-500 mt-1">{breakdown.recommendation}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
            <div className="rounded-lg bg-gray-950 p-3 border border-gray-800 text-center">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">Estimated Total Cost</p>
              <p className="text-2xl font-black text-emerald-400 mt-0.5">
                {currencySymbol}{breakdown.totalCost.toLocaleString()}
              </p>
            </div>
            <div className="rounded-lg bg-gray-950 p-3 border border-gray-800 text-center">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">Defect Count</p>
              <p className="text-2xl font-black text-gray-200 mt-0.5">
                {breakdown.items.length} <span className="text-xs font-normal text-gray-500">records</span>
              </p>
            </div>
            <div className="rounded-lg bg-gray-950 p-3 border border-gray-800 text-center">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">Surface Affected</p>
              <p className="text-2xl font-black text-purple-400 mt-0.5">
                {breakdown.totalAreaPct}% <span className="text-xs font-normal text-gray-500">area</span>
              </p>
            </div>
          </div>

          <div className="space-y-2 mb-4">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Itemized Work Estimates</p>
            {breakdown.items.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-lg border border-gray-800/80 bg-gray-950/60 px-3.5 py-2 text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <span className="h-2 w-2 rounded-full bg-red-500" />
                  <span className="font-bold text-gray-200 capitalize">{item.className.replace('_', ' ')}</span>
                  <span className="text-gray-500">({item.label})</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-gray-400 tabular-nums">{(item.confidence * 100).toFixed(0)}% conf</span>
                  <span className="font-mono font-bold text-emerald-400 tabular-nums">
                    +{currencySymbol}{item.cost}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg bg-emerald-950/20 border border-emerald-900/40 p-3 flex items-center gap-2 text-xs text-emerald-300">
            <span>💡</span>
            <span><strong className="font-bold text-emerald-200">Recommendation:</strong> {breakdown.recommendation}</span>
          </div>
        </>
      )}
    </div>
  );
}
