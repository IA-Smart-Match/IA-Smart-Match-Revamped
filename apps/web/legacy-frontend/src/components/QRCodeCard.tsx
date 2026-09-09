import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, QrCode } from "lucide-react";
import { toDataURL, toString } from "qrcode";

import type { FeedbackQrAsset } from "@/lib/api";

type QRCodeCardProps = {
  asset: FeedbackQrAsset | null;
  loading?: boolean;
  error?: string | null;
  onSave: (destinationUrl: string) => void | Promise<void>;
};

function hostname(value: string) {
  try {
    return new URL(value).hostname;
  } catch {
    return "External form";
  }
}

export function QRCodeCard({ asset, loading = false, error, onSave }: QRCodeCardProps) {
  const [destinationUrl, setDestinationUrl] = useState(asset?.destination_url ?? "");
  const [preview, setPreview] = useState("");
  const [svg, setSvg] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");
  const redirectUrl = useMemo(() => asset?.redirect_url ?? "", [asset]);

  useEffect(() => {
    setDestinationUrl(asset?.destination_url ?? "");
    setConfirmed(false);
  }, [asset]);
  useEffect(() => {
    let active = true;
    if (!redirectUrl) {
      setPreview("");
      setSvg("");
      return;
    }
    const options = {
      width: 640,
      margin: 2,
      color: { dark: "#005030", light: "#FFFFFF" },
      errorCorrectionLevel: "M",
    } as const;
    void Promise.all([
      toDataURL(redirectUrl, options),
      toString(redirectUrl, { ...options, type: "svg" }),
    ]).then(([pngValue, svgValue]) => {
      if (active) {
        setPreview(pngValue);
        setSvg(svgValue);
      }
    });
    return () => {
      active = false;
    };
  }, [redirectUrl]);

  function download() {
    if (!preview) return;
    const anchor = document.createElement("a");
    anchor.href = preview;
    anchor.download = "event-feedback-qr.png";
    anchor.click();
  }

  function downloadSvg() {
    if (!svg) return;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "event-feedback-qr.svg";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm" aria-labelledby="feedback-qr-heading">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <QrCode className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h2 id="feedback-qr-heading" className="text-xl font-semibold text-foreground">External feedback QR</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Add your organization’s feedback-form link. Smart Match records QR opens, then sends visitors to that external form.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[220px_1fr]">
        <div className="flex aspect-square items-center justify-center rounded-2xl border border-dashed border-border bg-muted/40 p-4">
          {preview ? <img src={preview} alt="QR code for the external event feedback form" className="h-full w-full object-contain" /> : <p className="text-center text-sm text-muted-foreground">Save a valid HTTPS form link to generate the QR code.</p>}
        </div>
        <div className="space-y-4">
          <div>
            <label htmlFor="feedback-url" className="mb-2 block text-sm font-medium">Feedback form URL</label>
            <input
              id="feedback-url"
              type="url"
              value={destinationUrl}
              onChange={(event) => {
                setDestinationUrl(event.target.value);
                setConfirmed(false);
                setSavedMessage("");
              }}
              placeholder="https://forms.example.edu/event-feedback"
              className="w-full rounded-xl border border-border bg-input-background px-4 py-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            />
            <p className="mt-2 text-xs text-muted-foreground">HTTPS links only. Smart Match does not host, inspect, or receive responses from this form.</p>
            <label className="mt-3 flex items-start gap-2 text-sm text-foreground">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" />
              I confirmed this link opens the intended external feedback form.
            </label>
          </div>

          {error ? <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</p> : null}
          {savedMessage ? <p role="status" className="rounded-xl bg-primary/5 px-4 py-3 text-sm text-primary">{savedMessage}</p> : null}

          {asset ? (
            <div className="rounded-xl bg-muted px-4 py-3 text-sm">
              <p className="font-medium text-foreground">Destination: {hostname(asset.destination_url)}</p>
              <p className="mt-1 text-muted-foreground">QR opens: {asset.open_count}</p>
              <p className="mt-1 text-muted-foreground">Generated {new Date(asset.created_at).toLocaleDateString()}</p>
              <a href={asset.destination_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 font-medium text-primary hover:underline">
                Check external link <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button type="button" disabled={loading || !destinationUrl.trim() || !confirmed} onClick={() => {
              setSavedMessage("");
              void Promise.resolve(onSave(destinationUrl.trim()))
                .then(() => setSavedMessage("Feedback QR link saved."))
                .catch(() => undefined);
            }} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
              {loading ? "Saving…" : asset ? "Update form link" : "Generate QR code"}
            </button>
            <button type="button" disabled={!preview || loading} onClick={download} className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-60">
              <Download className="h-4 w-4" aria-hidden="true" /> Download PNG
            </button>
            <button type="button" disabled={!svg || loading} onClick={downloadSvg} className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-60">
              <Download className="h-4 w-4" aria-hidden="true" /> Download SVG
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
