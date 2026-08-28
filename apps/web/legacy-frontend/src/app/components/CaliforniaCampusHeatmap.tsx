import { motion } from "motion/react";

/**
 * Demo-only California footprint: polished state outline + simulated campus/event density.
 * Coordinates are approximate (not survey-grade).
 */

const VIEW_W = 420;
const VIEW_H = 480;

const LON_MIN = -124.55;
const LON_MAX = -114.05;
const LAT_MIN = 32.45;
const LAT_MAX = 42.05;

function toSvg(lon: number, lat: number): { x: number; y: number } {
  const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * VIEW_W;
  const y = ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * VIEW_H;
  return { x, y };
}

/** More detailed California boundary. */
const CA_BORDER: Array<[number, number]> = [
  [42.0, -124.35], [42.0, -120.0], [39.0, -120.0], [35.0, -114.6], 
  [32.5, -114.7], [32.5, -117.1], [33.5, -118.2], [34.5, -120.6], 
  [36.5, -121.9], [37.8, -122.5], [38.5, -123.0], [40.0, -124.3], 
  [42.0, -124.35]
];

// Refined path for a smoother look
const CA_PATH = "M10.5,1.5 L175.5,1.5 L175.5,145.5 L395.5,365.5 L395.5,475.5 L305.5,475.5 L255.5,445.5 L155.5,405.5 L105.5,345.5 L65.5,285.5 L45.5,225.5 L10.5,145.5 Z";

const HEAT_BLOBS: Array<{ cx: number; cy: number; r: number; color: string }> = [
  { ...toSvg(-118.25, 34.05), r: 80, color: "var(--color-primary)" }, // LA
  { ...toSvg(-117.15, 32.88), r: 60, color: "var(--color-primary)" }, // SD
  { ...toSvg(-122.4, 37.77), r: 70, color: "var(--color-primary)" },  // SF/Bay
  { ...toSvg(-121.49, 38.58), r: 40, color: "var(--color-primary)" }, // Sac
  { ...toSvg(-119.75, 36.75), r: 50, color: "var(--color-primary)" }, // Fresno
];

type CampusKind = "csu" | "uc" | "cc" | "private" | "event";

const MARKERS: Array<{
  id: string;
  name: string;
  kind: CampusKind;
  lon: number;
  lat: number;
  weight: number;
}> = [
  { id: "ucla", name: "UCLA", kind: "uc", lon: -118.445, lat: 34.068, weight: 5 },
  { id: "ucsd", name: "UC San Diego", kind: "uc", lon: -117.234, lat: 32.88, weight: 5 },
  { id: "uci", name: "UC Irvine", kind: "uc", lon: -117.844, lat: 33.64, weight: 4 },
  { id: "berkeley", name: "UC Berkeley", kind: "uc", lon: -122.259, lat: 37.872, weight: 5 },
  { id: "davis", name: "UC Davis", kind: "uc", lon: -121.761, lat: 38.538, weight: 4 },
  { id: "csulb", name: "CSU Long Beach", kind: "csu", lon: -118.114, lat: 33.783, weight: 4 },
  { id: "sdsu", name: "San Diego State", kind: "csu", lon: -117.071, lat: 32.775, weight: 4 },
  { id: "fresno", name: "Fresno State", kind: "csu", lon: -119.746, lat: 36.813, weight: 3 },
  { id: "sac", name: "Sacramento State", kind: "csu", lon: -121.424, lat: 38.56, weight: 3 },
  { id: "cpp", name: "Cal Poly Pomona", kind: "csu", lon: -117.889, lat: 34.058, weight: 4 },
  { id: "smc", name: "Santa Monica College", kind: "cc", lon: -118.473, lat: 34.02, weight: 3 },
  { id: "sbcc", name: "Santa Barbara City College", kind: "cc", lon: -119.698, lat: 34.406, weight: 3 },
  { id: "deanza", name: "De Anza College", kind: "cc", lon: -122.032, lat: 37.32, weight: 4 },
  { id: "stanford", name: "Stanford", kind: "private", lon: -122.169, lat: 37.427, weight: 4 },
  { id: "usc", name: "USC", kind: "private", lon: -118.285, lat: 34.022, weight: 4 },
  { id: "pepperdine", name: "Pepperdine", kind: "private", lon: -118.71, lat: 34.041, weight: 2 },
  { id: "ev-la", name: "Hackathon · LA", kind: "event", lon: -118.32, lat: 34.15, weight: 3 },
  { id: "ev-sd", name: "Industry Night · SD", kind: "event", lon: -117.15, lat: 32.72, weight: 3 },
  { id: "ev-sf", name: "Bay Summit · SF", kind: "event", lon: -122.4, lat: 37.78, weight: 4 },
  { id: "ev-sj", name: "Campus Tour · San Jose", kind: "event", lon: -121.89, lat: 37.34, weight: 2 },
];

const KIND_STYLES: Record<
  CampusKind,
  { fill: string; stroke: string; label: string }
> = {
  csu: { fill: "#3b82f6", stroke: "#1d4ed8", label: "CSU" },
  uc: { fill: "#1e40af", stroke: "#1e3a8a", label: "UC" },
  cc: { fill: "#10b981", stroke: "#047857", label: "Community" },
  private: { fill: "#8b5cf6", stroke: "#6d28d9", label: "Private" },
  event: { fill: "#f59e0b", stroke: "#b45309", label: "Event" },
};

export function CaliforniaCampusHeatmap() {
  return (
    <div className="mt-8 overflow-hidden rounded-3xl border border-border/50 bg-white shadow-xl shadow-blue-500/5">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/40 bg-slate-50/50 px-6 py-4">
        <div>
          <h4 className="font-[Inter_Tight] text-base font-bold text-slate-900">Regional Footprint</h4>
          <p className="text-xs text-slate-500">Live campus engagements and chapter events</p>
        </div>
        <div className="flex flex-wrap gap-4">
          {(Object.keys(KIND_STYLES) as CampusKind[]).map((k) => (
            <div key={k} className="flex items-center gap-2">
              <div
                className="h-2.5 w-2.5 rounded-full shadow-sm"
                style={{ backgroundColor: KIND_STYLES[k].fill }}
              />
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600">
                {KIND_STYLES[k].label}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="relative aspect-[4/5] w-full p-8 md:p-12">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="mx-auto h-full w-full drop-shadow-2xl"
          style={{ filter: "drop-shadow(0 20px 30px rgba(0,0,0,0.05))" }}
        >
          <defs>
            <clipPath id="ca-clip">
              <path d={CA_PATH} />
            </clipPath>
            <radialGradient id="heat-grad">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.6" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* State Background */}
          <path
            d={CA_PATH}
            fill="#f8fafc"
            stroke="#e2e8f0"
            strokeWidth="2"
            className="transition-colors duration-500 hover:fill-slate-50"
          />

          {/* Heatmap Layer (Clipped to State) */}
          <g clipPath="url(#ca-clip)">
            {HEAT_BLOBS.map((blob, i) => (
              <motion.circle
                key={i}
                cx={blob.cx}
                cy={blob.cy}
                r={blob.r}
                fill="url(#heat-grad)"
                className="text-blue-400"
                initial={{ opacity: 0, scale: 0.5 }}
                whileInView={{ opacity: 1, scale: 1 }}
                transition={{ duration: 1.5, delay: i * 0.1, ease: "easeOut" }}
              />
            ))}
          </g>

          {/* Grid lines for texture */}
          <g className="opacity-[0.03]" pointerEvents="none">
            {Array.from({ length: 10 }).map((_, i) => (
              <line key={`h-${i}`} x1="0" y1={(VIEW_H / 10) * i} x2={VIEW_W} y2={(VIEW_H / 10) * i} stroke="black" />
            ))}
            {Array.from({ length: 10 }).map((_, i) => (
              <line key={`v-${i}`} x1={(VIEW_W / 10) * i} y1="0" x2={(VIEW_W / 10) * i} y2={VIEW_H} stroke="black" />
            ))}
          </g>

          {/* Markers */}
          {MARKERS.map((m, i) => {
            const { x, y } = toSvg(m.lon, m.lat);
            const style = KIND_STYLES[m.kind];
            const size = 4 + m.weight * 1.2;

            return (
              <motion.g
                key={m.id}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.03, duration: 0.4 }}
                className="cursor-pointer"
                whileHover={{ scale: 1.2, zIndex: 50 }}
              >
                <title>{`${m.name} (${style.label})`}</title>
                
                {/* Glow effect for events */}
                {m.kind === "event" && (
                  <motion.circle
                    r={size * 2}
                    cx={x}
                    cy={y}
                    fill={style.fill}
                    initial={{ opacity: 0.2, scale: 0.8 }}
                    animate={{ opacity: [0.1, 0.3, 0.1], scale: [1, 1.5, 1] }}
                    transition={{ repeat: Infinity, duration: 2 }}
                  />
                )}

                {m.kind === "event" ? (
                  <path
                    d={`M${x},${y-size*1.2} L${x+size},${y+size*0.8} L${x-size},${y+size*0.8} Z`}
                    fill={style.fill}
                    stroke="white"
                    strokeWidth="1.5"
                    className="drop-shadow-sm"
                  />
                ) : (
                  <circle
                    cx={x}
                    cy={y}
                    r={size}
                    fill={style.fill}
                    stroke="white"
                    strokeWidth="1.5"
                    className="drop-shadow-md"
                  />
                )}
              </motion.g>
            );
          })}

          <text
            x={VIEW_W - 20}
            y={VIEW_H - 20}
            textAnchor="end"
            className="select-none fill-slate-300 font-[Inter_Tight] text-[10px] font-bold uppercase tracking-[0.3em]"
          >
            California Sector
          </text>
        </svg>

        {/* Floating Stats or Labels could go here if needed */}
      </div>
      
      <div className="bg-slate-50/80 px-6 py-4 text-center border-t border-border/40">
        <p className="text-[11px] font-medium text-slate-400 uppercase tracking-widest">
          IA West Chapter • Operational Signal Density
        </p>
      </div>
    </div>
  );
}
