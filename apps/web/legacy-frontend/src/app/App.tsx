import { RouterProvider } from "react-router";
import { PrincipalQueryProvider } from "./components/PrincipalQueryProvider";
import { SessionProvider } from "./hooks/useSession";
import { router } from "./routes";

export default function App() {
  return (
    <SessionProvider>
      <PrincipalQueryProvider>
        <RouterProvider router={router} />
      </PrincipalQueryProvider>
    </SessionProvider>
  );
}
