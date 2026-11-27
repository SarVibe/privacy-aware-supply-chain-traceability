import { useState } from "react";
import { isAddress } from "ethers";
import { revokeStakeholder } from "../../services/api";

export default function RevokeStakeholder() {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleRevoke = async (event) => {
    event.preventDefault();
    setError("");
    setResult(null);

    const wallet = address.trim();

    if (!isAddress(wallet)) {
      setError("Enter a valid wallet address.");
      return;
    }

    if (!window.confirm(`Revoke stakeholder access for ${wallet}?`)) {
      return;
    }

    try {
      setLoading(true);

      const response = await revokeStakeholder({
        stakeholder_address: wallet,
      });

      setResult(response.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Revocation failed."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Revoke Stakeholder
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Revoke an authorized stakeholder wallet's access.
        </p>
      </div>

      <form
        onSubmit={handleRevoke}
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
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-red-500 focus:ring-2 focus:ring-red-200"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-red-600 px-4 py-2.5 font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Revoking..." : "Revoke Stakeholder"}
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
              Revocation Successful
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