import { useState } from "react";
import { isAddress } from "ethers";
import { registerStakeholder } from "../../services/api";

export default function RegisterStakeholder() {
  const [address, setAddress] = useState("");
  const [role, setRole] = useState("6");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleRegister = async (event) => {
    event.preventDefault();
    setError("");
    setResult(null);

    if (!isAddress(address.trim())) {
      setError("Enter a valid wallet address.");
      return;
    }

    try {
      setLoading(true);

      const response = await registerStakeholder({
        stakeholder_address: address.trim(),
        role: Number(role),
      });

      setResult(response.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Registration failed."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Register Stakeholder
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Authorize a stakeholder wallet and assign a role.
        </p>
      </div>

      <form
        onSubmit={handleRegister}
        className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div>
          <label
            htmlFor="walletAddress"
            className="mb-2 block text-sm font-medium text-slate-700"
          >
            Wallet Address
          </label>
          <input
            id="walletAddress"
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x..."
            required
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
          />
        </div>

        <div>
          <label
            htmlFor="stakeholderRole"
            className="mb-2 block text-sm font-medium text-slate-700"
          >
            Stakeholder Role
          </label>
          <select
            id="stakeholderRole"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
          >
            <option value="2">Manufacturer</option>
            <option value="3">Logistics Provider</option>
            <option value="4">Warehouse</option>
            <option value="5">Distributor</option>
            <option value="6">Pharmacy</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-blue-600 px-4 py-2.5 font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Registering..." : "Register Stakeholder"}
        </button>

        {error && (
          <p
            role="alert"
            className="rounded-lg bg-red-50 p-3 text-sm text-red-700"
          >
            {error}
          </p>
        )}

        {result && (
          <div className="rounded-lg bg-emerald-50 p-4">
            <h2 className="font-semibold text-emerald-800">
              Registration Successful
            </h2>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-sm text-emerald-900">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </form>
    </div>
  );
}