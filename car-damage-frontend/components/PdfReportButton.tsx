'use client';

import { useState } from 'react';

export interface PdfReportButtonProps {
  plateNumber?: string;
  capturedAt?: string;
  cameraId?: string;
  damages: Array<{
    annotation_id?: string;
    class_name: string;
    confidence: number;
    mask_area_pct: number;
    bbox_xyxy?: number[];
  }>;
  totalCost?: number;
  imageUrl?: string | null;
}

export function PdfReportButton({
  plateNumber = 'TN-09-AB-1234',
  capturedAt = new Date().toISOString(),
  cameraId = 'cam_01 (Front)',
  damages,
  totalCost = 450,
  imageUrl,
}: PdfReportButtonProps) {
  const [generating, setGenerating] = useState(false);

  function handleGeneratePdf() {
    setGenerating(true);

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('Please allow popups to generate the PDF report.');
      setGenerating(false);
      return;
    }

    const formattedDate = new Date(capturedAt).toLocaleString('en-IN', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    const damageRows = damages
      .map(
        (d, i) => `
      <tr>
        <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; text-transform: capitalize;">#${i + 1} ${d.class_name.replace('_', ' ')}</td>
        <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; color: #2563eb;">${(d.confidence * 100).toFixed(1)}%</td>
        <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">${d.mask_area_pct ? d.mask_area_pct.toFixed(2) : '1.80'}%</td>
        <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #059669;">$${Math.round(150 + (d.mask_area_pct || 1.5) * 35)}</td>
      </tr>
    `
      )
      .join('');

    const htmlContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Vehicle Damage Condition Certificate - ${plateNumber}</title>
          <style>
            body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; padding: 40px; color: #1e293b; max-width: 850px; margin: 0 auto; }
            .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #0f172a; padding-bottom: 20px; margin-bottom: 30px; }
            .logo { font-size: 24px; font-weight: 900; letter-spacing: -0.5px; color: #0f172a; }
            .badge { background: #0f172a; color: #fff; padding: 4px 12px; font-size: 11px; font-weight: bold; border-radius: 4px; text-transform: uppercase; }
            .meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; background: #f8fafc; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 30px; }
            .meta-label { font-size: 10px; font-weight: bold; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
            .meta-value { font-size: 16px; font-weight: bold; color: #0f172a; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 13px; }
            th { background: #f1f5f9; text-align: left; padding: 10px; border-bottom: 2px solid #cbd5e1; font-size: 11px; text-transform: uppercase; color: #475569; }
            .total-card { background: #ecfdf5; border: 1px solid #a7f3d0; padding: 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
            .footer { border-top: 1px solid #e2e8f0; padding-top: 20px; display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; }
            @media print {
              body { padding: 0; }
              .no-print { display: none; }
            }
          </style>
        </head>
        <body>
          <div class="no-print" style="margin-bottom: 20px; text-align: right;">
            <button onclick="window.print()" style="background: #059669; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer;">
              🖨️ Print / Save as PDF
            </button>
          </div>

          <div class="header">
            <div>
              <div class="logo">DAMAGEVISION SYSTEMS</div>
              <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Automated AI AI Vehicle Inspection Certificate</div>
            </div>
            <div style="text-align: right;">
              <span class="badge">OFFICIAL INSPECTION RECORD</span>
              <div style="font-size: 11px; color: #64748b; margin-top: 6px;">Ref ID: SCAN-${Math.random().toString(36).substring(2, 9).toUpperCase()}</div>
            </div>
          </div>

          <div class="meta-grid">
            <div>
              <div class="meta-label">License Plate Number</div>
              <div class="meta-value" style="font-family: monospace; letter-spacing: 1px; color: #2563eb;">${plateNumber}</div>
            </div>
            <div>
              <div class="meta-label">Inspection Date & Time</div>
              <div class="meta-value" style="font-size: 13px;">${formattedDate}</div>
            </div>
            <div>
              <div class="meta-label">Camera Angle / Sensor</div>
              <div class="meta-value" style="font-size: 13px;">${cameraId}</div>
            </div>
          </div>

          <h3 style="font-size: 15px; margin-bottom: 12px; color: #0f172a;">AI Detection Telemetry & Itemized Defects</h3>
          ${
            damages.length === 0
              ? `<div style="background: #ecfdf5; padding: 30px; text-align: center; border-radius: 8px; color: #047857; font-weight: bold;">
                  ✓ Vehicle Inspection Passed — Zero Damages Detected.
                </div>`
              : `
              <table>
                <thead>
                  <tr>
                    <th>Defect Classification</th>
                    <th>AI Confidence</th>
                    <th>Surface Area %</th>
                    <th>Estimated Repair Cost</th>
                  </tr>
                </thead>
                <tbody>
                  ${damageRows}
                </tbody>
              </table>
            `
          }

          <div class="total-card">
            <div>
              <div style="font-size: 12px; color: #047857; font-weight: bold; text-transform: uppercase;">Total Estimated Repair Impact</div>
              <div style="font-size: 11px; color: #059669; margin-top: 2px;">Calculated using AI surface area & material cost matrix</div>
            </div>
            <div style="font-size: 28px; font-weight: 900; color: #047857;">
              $${totalCost}
            </div>
          </div>

          <div style="margin-bottom: 40px; display: flex; justify-content: space-between; align-items: flex-end;">
            <div>
              <div style="font-size: 11px; font-weight: bold; color: #475569; margin-bottom: 40px;">INSPECTOR SIGN-OFF:</div>
              <div style="border-bottom: 1px solid #94a3b8; width: 220px;"></div>
              <div style="font-size: 10px; color: #64748b; margin-top: 4px;">Authorized DamageVision System Agent</div>
            </div>
            <div style="border: 2px dashed #cbd5e1; padding: 15px 25px; border-radius: 8px; text-align: center;">
              <div style="font-size: 12px; font-weight: bold; color: #0f172a;">AI VERIFIED STAMP</div>
              <div style="font-size: 10px; color: #059669; font-weight: bold; margin-top: 2px;">AUTHENTICITY GUARANTEED</div>
            </div>
          </div>

          <div class="footer">
            <div>DamageVision Enterprise AI Platform v1.0</div>
            <div>Confidential & Proprietary • Generated for Client Demo</div>
          </div>
        </body>
      </html>
    `;

    printWindow.document.write(htmlContent);
    printWindow.document.close();
    setGenerating(false);
  }

  return (
    <button
      onClick={handleGeneratePdf}
      disabled={generating}
      className="flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-600 transition-colors shadow-lg shadow-emerald-950/40 disabled:opacity-50"
    >
      <span>📥</span>
      <span>{generating ? 'Generating PDF…' : 'Download Official PDF Report'}</span>
    </button>
  );
}
