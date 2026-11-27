
import { Routes, Route, Navigate } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";

import AppLayout from "./components/layout/AppLayout";

import ProtectedRoute from "./routes/ProtectedRoute";
import RoleRoute from "./routes/RoleRoute";
import GenerateProof from "./pages/manufacturer/GenerateProof";
import VerifyZKP from "./pages/stakeholder/VerifyZKP";
import RegisterStakeholder from "./pages/admin/RegisterStakeholder";
import RevokeStakeholder from "./pages/admin/RevokeStakeholder";
import VerificationHistory from "./pages/stakeholder/VerificationHistory";
import StorageHistory from "./pages/manufacturer/StorageHistory";
import ManufacturerVerificationHistory from "./pages/manufacturer/ManufacturerVerificationHistory";

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
            <Route
              path="/admin/register"
              element={<RegisterStakeholder />}
            />
            <Route
              path="/admin/revoke"
              element={<RevokeStakeholder />}
            />
          </Route>

          {/* Manufacturer Routes */}
          <Route element={<RoleRoute allowedRoles={["Manufacturer"]} />}>
            <Route
              path="/manufacturer/generate-proof"
              element={<GenerateProof />}
            />

            <Route
              path="/manufacturer/storage-history"
              element={<StorageHistory />}
            />

            <Route
              path="/manufacturer/verification-history"
              element={<ManufacturerVerificationHistory />}
            />
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
            <Route path="/verify" element={<VerifyZKP />} />
          </Route>

          <Route
            element={
              <RoleRoute
                allowedRoles={[
                  "Manufacturer",
                  "Logistics Provider",
                  "Warehouse",
                  "Distributor",
                  "Pharmacy",
                ]}
              />
            }
          >
            <Route path="/history" element={<VerificationHistory />} />
          </Route>

        </Route>
      </Route>

      {/* Unknown routes */}
      <Route path="*" element={<Navigate to="/" replace />} />

    </Routes>
  );
}

export default App;
