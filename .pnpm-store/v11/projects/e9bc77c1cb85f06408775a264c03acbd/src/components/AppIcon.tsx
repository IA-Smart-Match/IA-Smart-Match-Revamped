import { Icon, type IconProps } from "@iconify/react";

export type AppIconName =
  | "points"
  | "membership"
  | "attendance"
  | "connect"
  | "calendar"
  | "events"
  | "outreach"
  | "meetings"
  | "schedule"
  | "qr"
  | "sparkles"
  | "warning"
  | "success"
  | "staffing"
  | "discover"
  | "matching"
  | "pipeline";

const ICON_REGISTRY: Record<AppIconName, string> = {
  points: "solar:medal-ribbon-star-bold-duotone",
  membership: "solar:star-bold-duotone",
  attendance: "solar:clipboard-check-bold-duotone",
  connect: "solar:users-group-rounded-bold-duotone",
  calendar: "solar:calendar-mark-bold-duotone",
  events: "solar:calendar-bold-duotone",
  outreach: "solar:letter-bold-duotone",
  meetings: "solar:video-frame-bold-duotone",
  schedule: "solar:clock-circle-bold-duotone",
  qr: "solar:qr-code-bold-duotone",
  sparkles: "solar:magic-stick-3-bold-duotone",
  warning: "solar:danger-triangle-bold-duotone",
  success: "solar:check-circle-bold-duotone",
  staffing: "solar:users-group-rounded-bold-duotone",
  discover: "solar:magnifer-bold-duotone",
  matching: "solar:cpu-bold-duotone",
  pipeline: "solar:chart-2-bold-duotone",
};

interface AppIconProps extends Omit<IconProps, "icon"> {
  name: AppIconName;
}

/**
 * Central icon wrapper for a consistent visual language across app surfaces.
 */
export function AppIcon({ name, ...props }: AppIconProps) {
  return <Icon icon={ICON_REGISTRY[name]} {...props} />;
}
