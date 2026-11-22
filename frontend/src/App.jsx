
import { Routes, Route, Navigate } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";

import AppLayout from "./components/layout/AppLayout";

import ProtectedRoute from "./routes/ProtectedRoute";
import RoleRoute from "./routes/RoleRoute";

function App() {
  return (
    <Routes>

      {/* Public Landing Page */}
      <Route path="/" element={<LandingPage />} />

      {/* Protected Application Pages */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>

          <Route path="/dashboard" element={<Dashboard />} />

          {/* Admin Routes */}
          <Route element={<RoleRoute allowedRoles={["Admin"]} />}>
            {/* Admin pages will be added here */}
          </Route>

          {/* Manufacturer Routes */}
          <Route element={<RoleRoute allowedRoles={["Manufacturer"]} />}>
            {/* Manufacturer pages will be added here */}
          </Route>

          {/* Other Stakeholder Routes */}
          <Route
            element={
              <RoleRoute
                allowedRoles={[
                  "Logistics Provider",
                  "Warehouse",
                  "Distributor",
                  "Pharmacy",
                ]}
              />
            }
          >
            {/* Stakeholder pages will be added here */}
          </Route>

        </Route>
      </Route>

      {/* Unknown routes */}
      <Route path="*" element={<Navigate to="/" replace />} />

    </Routes>
  );
}

export default App;
