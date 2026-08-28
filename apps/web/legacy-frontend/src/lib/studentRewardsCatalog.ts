import type { LucideIcon } from "lucide-react";

import { BadgeCheck, BookOpen, Briefcase, Gift, GraduationCap, Linkedin } from "lucide-react";

export type RewardCategoryId = "linkedin" | "platforms" | "certs" | "growth";

export type StudentRewardItem = {
  id: string;
  title: string;
  subtitle: string;
  pointsCost: number;
  category: RewardCategoryId;
  icon: LucideIcon;
};

export const REWARD_CATEGORY_LABELS: Record<RewardCategoryId, string> = {
  linkedin: "LinkedIn",
  platforms: "Learning platforms",
  certs: "Certificates",
  growth: "Professional growth",
};

export const STUDENT_REWARD_CATALOG: StudentRewardItem[] = [
  {
    id: "linkedin-premium-1m",
    title: "LinkedIn Premium",
    subtitle: "1 month — Career insights, InMail credits, and applicant insights.",
    pointsCost: 5000,
    category: "linkedin",
    icon: Linkedin,
  },
  {
    id: "linkedin-premium-12m",
    title: "LinkedIn Premium",
    subtitle: "12 months — Best value annual access for active job seekers.",
    pointsCost: 45000,
    category: "linkedin",
    icon: Linkedin,
  },
  {
    id: "coursera-cert",
    title: "Coursera Professional Certificate",
    subtitle: "One guided program from a university or industry partner of your choice.",
    pointsCost: 8500,
    category: "certs",
    icon: GraduationCap,
  },
  {
    id: "google-cert",
    title: "Google Career Certificate",
    subtitle: "Data Analytics, UX, Project Management, or IT Support — voucher toward enrollment.",
    pointsCost: 12000,
    category: "certs",
    icon: BadgeCheck,
  },
  {
    id: "udemy-business",
    title: "Udemy Business",
    subtitle: "3 months — Unlimited courses including tech and leadership libraries.",
    pointsCost: 3200,
    category: "platforms",
    icon: BookOpen,
  },
  {
    id: "industry-mentor",
    title: "IA West mentor session",
    subtitle: "60-minute 1:1 with a volunteer leader in your target field (scheduling coordinated by chapter).",
    pointsCost: 2500,
    category: "growth",
    icon: Briefcase,
  },
  {
    id: "conference-stipend",
    title: "Conference stipend",
    subtitle: "$250 toward registration or travel for an insights / analytics event (approved list).",
    pointsCost: 15000,
    category: "growth",
    icon: Gift,
  },
];

export function rewardsSortedByPoints(): StudentRewardItem[] {
  return [...STUDENT_REWARD_CATALOG].sort((a, b) => a.pointsCost - b.pointsCost);
}
