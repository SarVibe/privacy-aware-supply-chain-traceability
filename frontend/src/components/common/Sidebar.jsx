
import { NavLink } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const sidebarItems = {
  Admin: [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Register Stakeholder", path: "/admin/register" },
    { label: "Revoke Stakeholder", path: "/admin/revoke" },
  ],

  Manufacturer: [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Generate ZKP", path: "/manufacturer/generate-proof" },
    { label: "Verification History", path: "/history" },
  ],

  "Logistics Provider": [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Verify ZKP", path: "/verify" },
    { label: "Verification History", path: "/history" },
  ],

  Warehouse: [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Verify ZKP", path: "/verify" },
    { label: "Verification History", path: "/history" },
  ],

  Distributor: [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Verify ZKP", path: "/verify" },
    { label: "Verification History", path: "/history" },
  ],

  Pharmacy: [
    { label: "Dashboard", path: "/dashboard" },
    { label: "Verify ZKP", path: "/verify" },
    { label: "Verification History", path: "/history" },
  ],
};

function Sidebar() {
  const { user } = useAuth();

  const items = sidebarItems[user?.roleName] || [];

  return (
    <aside className="min-h-[calc(100vh-4rem)] w-64 border-r border-slate-200 bg-slate-900 px-4 py-6">

      <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Main Menu
      </p>

      <nav className="space-y-2">
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end
            className={({ isActive }) =>
              `block rounded-lg px-4 py-3 text-sm font-medium transition ${
                isActive
                  ? "bg-cyan-500 text-slate-950"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-10 border-t border-slate-700 px-3 pt-5">
        <p className="text-xs text-slate-400">
          Logged in as
        </p>

        <p className="mt-1 text-sm font-semibold text-white">
          {user?.roleName}
        </p>
      </div>

    </aside>
  );
}

export default Sidebar;
