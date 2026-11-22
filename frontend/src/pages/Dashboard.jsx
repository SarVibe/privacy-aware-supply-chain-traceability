
import { useAuth } from "../context/AuthContext";

function Dashboard() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">

      {/* Page heading */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Dashboard
        </h1>

        <p className="mt-1 text-sm text-slate-500">
          Welcome to the C3 ZKP Supply Chain Verification System.
        </p>
      </div>

      {/* Welcome card */}
      <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-cyan-900 p-8 text-white shadow-lg">

        <p className="text-sm text-cyan-300">
          Welcome back
        </p>

        <h2 className="mt-2 text-3xl font-bold">
          {user?.roleName}
        </h2>

        <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">
          You are connected as an authorized stakeholder.
          Use the navigation menu to access your available
          supply chain verification operations.
        </p>

      </div>

      {/* Information cards */}
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Stakeholder Role
          </p>

          <h3 className="mt-3 text-xl font-bold text-slate-900">
            {user?.roleName}
          </h3>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Blockchain Network
          </p>

          <h3 className="mt-3 text-xl font-bold text-slate-900">
            Local Hardhat
          </h3>

          <p className="mt-1 text-xs text-slate-500">
            Chain ID: {user?.chainId}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">
            Wallet Status
          </p>

          <h3 className="mt-3 text-xl font-bold text-green-600">
            Connected
          </h3>
        </div>

      </div>

    </div>
  );
}

export default Dashboard;
