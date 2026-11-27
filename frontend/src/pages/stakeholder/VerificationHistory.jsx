import { useEffect, useState } from "react";
import { getVerificationHistory } from "../../services/api";

const ATTRIBUTE_NAMES = [
  "product id",
  "product name",
  "batch number",
  "manufacturing date",
  "expiry date",
  "manufacturer id",
  "shipment id",
  "quantity",
  "source location",
  "destination location",
];

function VerificationHistory() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHistory = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await getVerificationHistory();
      setHistory(response.data.history || []);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Unable to retrieve verification history."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const getVerifiedAttributes = (mask) =>
    ATTRIBUTE_NAMES.filter(
      (_, index) => (Number(mask) & (1 << index)) !== 0
    ).join(", ");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Verification History
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          View your blockchain verification transactions.
        </p>
      </div>

      <button
        onClick={loadHistory}
        disabled={loading}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Loading..." : "Refresh History"}
      </button>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && history.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          No verification transactions found.
        </div>
      )}

      {history.map((item) => (
        <div
          key={item.transaction_hash}
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-800">
              Record ID: {item.record_id}
            </h2>
            <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-700">
              {item.status}
            </span>
          </div>

          <div className="space-y-2 text-sm text-slate-700">
            <p>
              <strong>Role:</strong> {item.role}
            </p>
            <p>
              <strong>Block Number:</strong> {item.block_number}
            </p>
            <p>
              <strong>Gas Used:</strong> {item.gas_used}
            </p>
            <p>
              <strong>Verified At:</strong>{" "}
              {new Date(item.timestamp * 1000).toLocaleString()}
            </p>
            <p className="break-all">
              <strong>Transaction Hash:</strong>{" "}
              {item.transaction_hash}
            </p>
            <p>
              <strong>Verified Attributes:</strong>{" "}
              {getVerifiedAttributes(item.attribute_mask)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default VerificationHistory;