import { RouterProvider } from "react-router";
import { PrincipalQueryProvider } from "./components/PrincipalQueryProvider";
import { router } from "./routes";

export default function App() {
  return (
    <PrincipalQueryProvider>
      <RouterProvider router={router} />
    </PrincipalQueryProvider>
  );
}
