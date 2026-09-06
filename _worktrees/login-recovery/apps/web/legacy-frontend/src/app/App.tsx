import { RouterProvider } from "react-router";
import { PrincipalQueryProvider } from "./components/PrincipalQueryProvider";
import { PortalAccessProvider } from "./hooks/usePortalAccess";
import { SessionProvider } from "./hooks/useSession";
import { router } from "./routes";

/**
 * `PortalAccessProvider` sits *inside* `SessionProvider` and outside the
 * router, in that order for two reasons. It reads `useSession()`, so the
 * session must already be in context; and every portal shell consumes the
 * mapping, so hoisting it above the router means one `GET /v1/me/portals` per
 * signed-in principal rather than one per shell that happens to mount.
 */
export default function App() {
  return (
    <SessionProvider>
      <PortalAccessProvider>
        <PrincipalQueryProvider>
          <RouterProvider router={router} />
        </PrincipalQueryProvider>
      </PortalAccessProvider>
    </SessionProvider>
  );
}
