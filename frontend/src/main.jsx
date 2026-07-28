import React from "react";
import { createRoot } from "react-dom/client";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LandingPage } from "./pages/LandingPage";
import "./styles.css";

function App() {
  const [path, setPath] = React.useState(window.location.pathname);

  React.useEffect(() => {
    const updatePath = () => setPath(window.location.pathname);
    window.addEventListener("popstate", updatePath);
    return () => window.removeEventListener("popstate", updatePath);
  }, []);

  if (path === "/login" || path === "/signup") {
    return <AuthPage mode={path === "/signup" ? "signup" : "login"} />;
  }

  if (path === "/dashboard") {
    const role = new URLSearchParams(window.location.search).get("role") === "officer" ? "officer" : "analyst";
    return <DashboardPage role={role} />;
  }

  return <LandingPage />;
}

createRoot(document.getElementById("root")).render(<App />);
