const AVATAR_POOL_SIZE = 70;

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

/**
 * Returns a deterministic, LinkedIn-style generic profile image URL.
 * We intentionally use a seeded avatar service so mock users are stable.
 */
export function getMockProfilePhoto(seed: string): string {
  const normalized = seed.trim().toLowerCase() || "mock-profile";
  const index = (hashString(normalized) % AVATAR_POOL_SIZE) + 1;
  return `https://i.pravatar.cc/160?img=${index}`;
}

export function getInitials(name: string): string {
  return String(name || "?")
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
