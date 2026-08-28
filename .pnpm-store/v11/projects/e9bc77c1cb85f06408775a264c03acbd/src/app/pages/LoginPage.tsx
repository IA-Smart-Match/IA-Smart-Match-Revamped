import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { GraduationCap, Building, ShieldCheck, Briefcase } from "lucide-react";
import { BrandLogo } from "../components/BrandLogo";

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
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const roleFromUrl = searchParams.get("role") as "student" | "event_coordinator" | "ia_admin" | "volunteer" | null;
  const [selectedRole, setSelectedRole] = useState<"student" | "event_coordinator" | "ia_admin" | "volunteer">(roleFromUrl ?? "student");
  const [email, setEmail] = useState(() => {
    const initial = roleFromUrl ?? "student";
    return ROLES.find((r) => r.key === initial)?.email ?? "";
  });
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleLogin(_email: string, role: string, _password: string) {
    setLoading(true);
    const destination =
      role === "student"
        ? "/student-portal"
        : role === "event_coordinator"
          ? "/coordinator-portal"
          : role === "volunteer"
            ? "/volunteer-portal"
            : "/dashboard";
    navigate(destination);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    handleLogin(email, selectedRole, password);
  }

  const selectedRoleLabel = ROLES.find((role) => role.key === selectedRole)?.label ?? "Student";

  return (
    <div className="public-shell min-h-screen">
      <header className="fixed inset-x-0 top-0 z-50 border-b border-border/70 bg-background/90 backdrop-blur-xl">
        <nav className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-6 lg:px-8">
          <BrandLogo
            href="/"
            direction="row"
            imageClassName="h-9"
            showBadge={false}
          />
          <Link to="/" className="text-sm font-medium text-muted-foreground transition hover:text-primary">
            Back to home
          </Link>
        </nav>
      </header>

      <main className="flex min-h-screen items-center justify-center px-6 pb-12 pt-28 lg:px-8">
        <section className="relative w-full max-w-xl">
          <div className="public-panel relative overflow-hidden">
            <div className="px-6 py-7 sm:px-8 sm:py-8">
              <div className="text-center">
                <h2 className="mt-4 font-[Inter_Tight] text-4xl font-semibold tracking-tight text-foreground">
                  Log in
                </h2>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  Use your email and password to access the workspace.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="mt-8 space-y-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground" htmlFor="login-email">
                    Login, email, or phone number
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
                  <label className="mb-1.5 block text-sm font-medium text-muted-foreground" htmlFor="login-password">
                    Password
                  </label>
                  <input
                    id="login-password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="w-full rounded-2xl border border-border/70 bg-surface-container-low px-4 py-3 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>

                {error && (
                  <p className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {error}
                  </p>
                )}

                <button type="submit" disabled={loading} className="public-button-primary w-full rounded-2xl py-3.5 disabled:opacity-60">
                  {loading ? "Signing in…" : "Log in"}
                </button>
              </form>

              <div className="mt-6 rounded-[1.4rem] border border-border/70 bg-surface-container-low p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Choose your workspace</p>
                    <p className="mt-1 text-xs text-muted-foreground">Select a role to continue to the right workspace.</p>
                  </div>
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                    {selectedRoleLabel}
                  </span>
                </div>

                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {ROLES.map((role) => {
                    const Icon = role.icon;
                    const active = selectedRole === role.key;

                    function selectRole() {
                      setSelectedRole(role.key);
                      setEmail(role.email);
                    }

                    return (
                      <button
                        key={role.key}
                        type="button"
                        onClick={selectRole}
                        className={`flex items-center gap-3 rounded-2xl border px-3 py-3 text-left transition ${
                          active
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-border/70 bg-white hover:border-primary/30 hover:bg-primary/5"
                        }`}
                      >
                        <span
                          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors ${
                            active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                          }`}
                        >
                          <Icon className="h-5 w-5" />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-foreground">{role.label}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
