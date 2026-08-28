import { Download, QrCode, Sparkles, ScanSearch } from "lucide-react";

import type { QrCodeAsset } from "@/lib/api";

type QRCodeCardProps = {
  asset: QrCodeAsset | null;
  loading?: boolean;
  error?: string | null;
  title?: string;
  description?: string;
  primaryActionLabel?: string;
  secondaryActionLabel?: string;
  onPrimaryAction?: () => void | Promise<void>;
  className?: string;
};

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "qr";
}

function formatDate(value: string) {
  if (!value) {
    return "Not generated yet";
  }

  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function resolvePreviewSource(asset: QrCodeAsset) {
  if (asset.qr_png_data_url) {
    return asset.qr_png_data_url;
  }
  if (asset.qr_svg_data_url) {
    return asset.qr_svg_data_url;
  }
  if (asset.qr_svg) {
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(asset.qr_svg)}`;
  }
  if (asset.qr_image_url) {
    return asset.qr_image_url;
  }
  if (asset.download_url) {
    return asset.download_url;
  }
  return "";
}

function resolveDownloadHref(asset: QrCodeAsset) {
  return (
    asset.download_url ||
    asset.qr_png_data_url ||
    asset.qr_svg_data_url ||
    asset.qr_image_url ||
    resolvePreviewSource(asset)
  );
}

function resolveFilename(asset: QrCodeAsset) {
  const base = slugify(`${asset.speaker_name || "speaker"}-${asset.event_name || "event"}-${asset.referral_code || "qr"}`);
  const usesPng =
    Boolean(asset.qr_png_data_url) ||
    asset.qr_image_url.toLowerCase().includes(".png") ||
    asset.download_url.toLowerCase().includes(".png");
  return `${base}.${usesPng ? "png" : "svg"}`;
}

async function downloadAsset(asset: QrCodeAsset) {
  const href = resolveDownloadHref(asset);
  const filename = resolveFilename(asset);

  if (!href) {
    return;
  }

  const anchor = document.createElement("a");
  anchor.download = filename;

  if (asset.qr_svg) {
    const blob = new Blob([asset.qr_svg], { type: "image/svg+xml;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    anchor.href = objectUrl;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    return;
  }

  if (asset.qr_svg_data_url || asset.qr_png_data_url || asset.download_url) {
    anchor.href = href;
    anchor.click();
    return;
  }

  if (asset.qr_image_url) {
    try {
      const response = await fetch(asset.qr_image_url);
      if (response.ok) {
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        anchor.href = objectUrl;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
        return;
      }
    } catch {
      // Fall through to the direct link behavior below.
    }
  }

  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  anchor.click();
}

export function QRCodeCard({
  asset,
  loading = false,
  error = null,
  title = "QR referral asset",
  description = "Generate and download a branded speaker-event QR code.",
  primaryActionLabel,
  secondaryActionLabel = "Download QR",
  onPrimaryAction,
  className = "",
}: QRCodeCardProps) {
  const previewSource = asset ? resolvePreviewSource(asset) : "";
  const canDownload = Boolean(asset);
  const primaryLabel = primaryActionLabel ?? (asset ? "Refresh QR" : "Generate QR");

  return (
    <section
      className={`overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-sky-50/60 to-blue-50 shadow-sm ${className}`}
    >
      <div className="border-b border-slate-200/80 bg-white/80 px-5 py-4 backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-100 text-blue-700">
                <QrCode className="h-4 w-4" />
              </span>
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
                <p className="text-sm text-slate-600">{description}</p>
              </div>
            </div>
          </div>
          <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
            IA West QR
          </span>
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex aspect-square items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50">
            {loading ? (
              <div className="h-full w-full animate-pulse rounded-xl bg-gradient-to-br from-slate-200 to-slate-100" />
            ) : previewSource ? (
              // The QR preview may be SVG markup, a data URL, or a hosted image.
              <img
                src={previewSource}
                alt={asset ? `${asset.speaker_name} referral QR` : "QR preview"}
                className="h-full w-full rounded-xl object-contain p-3"
              />
            ) : (
              <div className="flex flex-col items-center gap-2 px-4 text-center text-slate-500">
                <QrCode className="h-10 w-10 text-slate-300" />
                <p className="text-sm font-medium">No QR generated yet</p>
                <p className="text-xs leading-5">
                  Create a referral QR for the selected speaker and event.
                </p>
              </div>
            )}
          </div>

          <div className="mt-4 space-y-2">
            {asset ? (
              <>
                <div className="rounded-xl bg-slate-50 px-3 py-2">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Referral code</p>
                  <p className="truncate text-sm font-semibold text-slate-900">
                    {asset.referral_code}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 px-3 py-2">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Generated</p>
                  <p className="text-sm font-medium text-slate-900">{formatDate(asset.generated_at)}</p>
                </div>
              </>
            ) : (
              <div className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600">
                The QR asset is empty until you generate the current speaker-event pair.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {error ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {error}
            </div>
          ) : null}

          {asset ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-slate-500">Speaker</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{asset.speaker_name}</p>
                <p className="text-xs text-slate-600">{asset.speaker_title || "Speaker profile"}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-slate-500">Event</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{asset.event_name}</p>
                <p className="text-xs text-slate-600">{asset.speaker_company || "IA West volunteer"}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-slate-500">Scans</p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">{asset.scan_count}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-slate-500">Conversions</p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">{asset.conversion_count}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm sm:col-span-2">
                <p className="text-xs uppercase tracking-wide text-slate-500">ROI</p>
                <div className="mt-2 flex items-center gap-3">
                  <div className="h-2 flex-1 rounded-full bg-slate-100">
                    <div
                      className="h-2 rounded-full bg-gradient-to-r from-blue-600 to-sky-500"
                      style={{ width: `${Math.round(asset.conversion_rate * 100)}%` }}
                    />
                  </div>
                  <span className="text-sm font-semibold text-slate-900">
                    {Math.round(asset.conversion_rate * 100)}%
                  </span>
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm sm:col-span-2">
                <p className="text-xs uppercase tracking-wide text-slate-500">Destination</p>
                <p className="mt-1 truncate text-sm font-medium text-slate-900">
                  {asset.destination_url || asset.scan_url || "Not linked yet"}
                </p>
                <p className="mt-1 text-xs text-slate-600">
                  Last scan: {asset.last_scanned_at ? formatDate(asset.last_scanned_at) : "No scans yet"}
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-blue-200 bg-white/80 p-6">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                  <ScanSearch className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-slate-900">No QR asset yet</h4>
                  <p className="mt-1 text-sm text-slate-600">
                    Generate the current referral code to preview the QR, download it, and track scans.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            {onPrimaryAction ? (
              <button
                type="button"
                onClick={() => void onPrimaryAction()}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
                disabled={loading}
              >
                <Sparkles className="h-4 w-4" />
                {primaryLabel}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => asset && void downloadAsset(asset)}
              disabled={!canDownload || loading}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
            >
              <Download className="h-4 w-4" />
              {secondaryActionLabel}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
