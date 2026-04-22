import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { isAuthed } from "./auth";
import { Shell } from "./components/Shell";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Keys from "./pages/Keys";
import Usage from "./pages/Usage";
import Jobs from "./pages/Jobs";

function Protected({ children }: { children: ReactElement }) {
  if (!isAuthed()) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Overview /></Protected>} />
      <Route path="/keys" element={<Protected><Keys /></Protected>} />
      <Route path="/usage" element={<Protected><Usage /></Protected>} />
      <Route path="/jobs" element={<Protected><Jobs /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
