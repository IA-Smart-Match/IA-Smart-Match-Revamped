import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { motion } from "motion/react";
import { GraduationCap, Building, ShieldCheck, Briefcase } from "lucide-react";
import { mockLogin } from "../../lib/api";

const panelReveal = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
} as const;

const ROLES = [
  {
    key: "student" as const,
    label: "Student",
    description: "View events, track attendance & get matched",
    icon: GraduationCap,
    email: "alex.rivera@cal.edu",
  },
  {
    key: "event_coordinator" as const,
    label: "Event Coordinator",
    description: "Manage events, outreach & IA West contact",
    icon: Building,
    email: "jordan.lee@cpp.edu",
  },
  {
    key: "ia_admin" as const,
    label: "IA West Admin",
    description: "Full admin access across all portals",
    icon: ShieldCheck,
    email: "admin@iawest.org",
  },
  {
    key: "volunteer" as const,
    label: "Volunteer / Speaker",
    description: "View your assignments, match score & speaker profile",
    icon: Briefcase,
    email: "shana.demarinis@testset.com",
  },
];

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const roleFromUrl = searchParams.get("role") as "student" | "event_coordinator" | "ia_admin" | "volunteer" | null;
  const [selectedRole, setSelectedRole] = useState<"student" | "event_coordinator" | "ia_admin" | "volunteer">(roleFromUrl ?? "student");
  const [email, setEmail] = useState(() => {
    const initial = roleFromUrl ?? "student";
    return ROLES.find((r) => r.key === initial)?.email ?? "";
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(email: string, role: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await mockLogin(email, role);
      sessionStorage.setItem("iaw_session", JSON.stringify({ user: response.user, role: response.role }));
      navigate(response.redirect_path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await handleLogin(email, selectedRole);
  }

  return (
    <div className="public-shell">
      <header className="border-b border-border/70 bg-background/85 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20">
              IW
            </span>
            <div className="leading-tight">
              <p className="font-semibold text-foreground">IA West Smart Match</p>
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Portal login</p>
            </div>
          </Link>
          <Link to="/" className="text-sm font-medium text-muted-foreground transition hover:text-primary">
            Back to home
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12 lg:px-8 lg:py-16">
        <motion.div {...panelReveal} className="mb-10 space-y-3 text-center">
          <span className="public-pill">Demo Access</span>
          <h1 className="font-[Inter_Tight] text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
            Choose your portal
          </h1>
          <p className="mx-auto max-w-xl text-base leading-7 text-muted-foreground">
            Select a role to explore the IA West Smart Match platform with pre-loaded demo data.
          </p>
        </motion.div>

        {/* Role picker cards */}
        <motion.div
          {...panelReveal}
          transition={{ ...panelReveal.transition, delay: 0.06 }}
          className="mb-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {ROLES.map((role) => {
            const Icon = role.icon;
            const isSelected = selectedRole === role.key;
            function selectRole() {
              setSelectedRole(role.key);
              setEmail(role.email);
            }
            return (
              <div
                key={role.key}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    selectRole();
                  }
                }}
                onClick={selectRole}
                className={`group flex cursor-pointer flex-col rounded-2xl border p-6 text-left transition-all ${
                  isSelected
                    ? "border-primary bg-primary/5 shadow-sm ring-2 ring-primary/30"
                    : "border-border/70 bg-card hover:border-primary/40 hover:bg-primary/5"
                }`}
              >
                <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-xl transition-colors ${isSelected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <p className="font-semibold text-foreground">{role.label}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{role.description}</p>
                <p className="mt-3 text-xs text-muted-foreground/70">{role.email}</p>
              </div>
            );
          })}
        </motion.div>

        {/* Divider */}
        <div className="mb-8 flex items-center gap-4">
          <div className="h-px flex-1 bg-border/70" />
          <span className="text-xs text-muted-foreground">or sign in manually</span>
          <div className="h-px flex-1 bg-border/70" />
        </div>

        {/* Manual login form */}
        <motion.section
          {...panelReveal}
          transition={{ ...panelReveal.transition, delay: 0.1 }}
          className="mx-auto max-w-md"
        >
          <div className="public-panel overflow-hidden">
            <div className="border-b border-border/70 px-6 py-5">
              <p className="public-pill">Custom Login</p>
              <h2 className="mt-3 font-[Inter_Tight] text-2xl font-semibold text-foreground">
                Sign in with email
              </h2>
            </div>
            <div className="px-6 py-6">
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground" htmlFor="login-email">
                    Email
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your@email.com"
                    className="w-full rounded-2xl border border-border/70 bg-surface-container-low px-4 py-3 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground" htmlFor="login-role">
                    Role
                  </label>
                  <select
                    id="login-role"
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value as "student" | "event_coordinator" | "ia_admin" | "volunteer")}
                    className="w-full rounded-2xl border border-border/70 bg-surface-container-low px-4 py-3 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  >
                    <option value="student">Student</option>
                    <option value="event_coordinator">Event Coordinator</option>
                    <option value="ia_admin">IA West Admin</option>
                    <option value="volunteer">Volunteer / Speaker</option>
                  </select>
                </div>
                {error && (
                  <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
                    {error}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={loading}
                  className="public-button-primary w-full disabled:opacity-60"
                >
                  {loading ? "Signing in…" : "Sign In"}
                </button>
              </form>
            </div>
          </div>
        </motion.section>
      </main>
    </div>
  );
}
