import { useState } from "react";
import { generateZKPProof } from "../../services/api";

// Define the ten supply-chain attributes used by the ZKP circuit.
const ATTRIBUTES = [
  { name: "product_id", label: "Product ID" },
  { name: "product_name", label: "Product Name" },
  { name: "batch_number", label: "Batch Number" },
  { name: "manufacturing_date", label: "Manufacturing Date (YYYYMMDD)" },
  { name: "expiry_date", label: "Expiry Date (YYYYMMDD)" },
  { name: "manufacturer_id", label: "Manufacturer ID" },
  { name: "shipment_id", label: "Shipment ID" },
  { name: "quantity", label: "Quantity" },
  { name: "source_location", label: "Source Location" },
  { name: "destination_location", label: "Destination Location" },
];

function GenerateProof() {
  // Store actual and expected values separately.
  const [actual, setActual] = useState({});
  const [expected, setExpected] = useState({});

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Update one actual or expected attribute.
  const handleChange = (type, attribute, value) => {
    if (type === "actual") {
      setActual((previous) => ({
        ...previous,
        [attribute]: value,
      }));
    } else {
      setExpected((previous) => ({
        ...previous,
        [attribute]: value,
      }));
    }
  };

  // Request proof generation from the authenticated backend.
  const handleSubmit = async (event) => {
    event.preventDefault();

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await generateZKPProof({
        actual,
        expected,
      });

      // Store the generated proof and its public verification data.
      setResult(response.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Unable to generate the ZKP proof."
      );
    } finally {
      setLoading(false);
    }
  };

  // Download only proof-related data, never raw supply-chain values.
  const downloadProof = () => {
    if (!result) return;

    const proofData = {
      format_version: "1.0",
      is_valid: result.is_valid,
      public_signals: result.public_signals,
      proof: result.proof,
      proof_generation_time_seconds:
        result.proof_generation_time_seconds,
      proof_verification_time_seconds:
        result.proof_verification_time_seconds,
    };

    const file = new Blob(
      [JSON.stringify(proofData, null, 2)],
      { type: "application/json" }
    );

    const url = URL.createObjectURL(file);
    const link = document.createElement("a");

    link.href = url;
    link.download = "supply-chain-zkp-proof.json";
    link.click();

    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Generate Zero-Knowledge Proof
        </h1>

        <p className="mt-2 text-sm text-slate-600">
          Generate a Groth16 proof to verify supply-chain
          information without sharing the original values.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-800">
            Supply Chain Information
          </h2>

          <p className="mt-2 text-sm text-slate-500">
            Enter the actual and expected values for all ten attributes.
          </p>

          <div className="mt-6 space-y-5">
            {ATTRIBUTES.map((attribute) => (
              <div
                key={attribute.name}
                className="grid grid-cols-1 gap-4 md:grid-cols-2"
              >
                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700">
                    {attribute.label} – Actual
                  </label>

                  <input
                    type="text"
                    required
                    value={actual[attribute.name] || ""}
                    onChange={(event) =>
                      handleChange(
                        "actual",
                        attribute.name,
                        event.target.value
                      )
                    }
                    placeholder={`Enter actual ${attribute.label.toLowerCase()}`}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700">
                    {attribute.label} – Expected
                  </label>

                  <input
                    type="text"
                    required
                    value={expected[attribute.name] || ""}
                    onChange={(event) =>
                      handleChange(
                        "expected",
                        attribute.name,
                        event.target.value
                      )
                    }
                    placeholder={`Enter expected ${attribute.label.toLowerCase()}`}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  />
                </div>
              </div>
            ))}
          </div>

          <p className="mt-5 text-xs text-slate-500">
            Dates must use YYYYMMDD format. Quantity must be a
            non-negative integer.
          </p>

          <button
            type="submit"
            disabled={loading}
            className="mt-6 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Generating ZKP..." : "Generate ZKP"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-800">
            Proof Generation Result
          </h2>

          <div
            className={`mt-4 rounded-lg p-4 text-sm font-semibold ${
              result.is_valid
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {result.is_valid
              ? "Valid – All supply-chain attributes match."
              : "Invalid – Supply-chain data mismatch detected."}
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">
                Proof Generation Time
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-800">
                {result.proof_generation_time_seconds?.toFixed(4)} s
              </p>
            </div>

            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">
                Proof Verification Time
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-800">
                {result.proof_verification_time_seconds?.toFixed(4)} s
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={downloadProof}
            className="mt-6 rounded-lg bg-green-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-green-700"
          >
            Download Proof JSON
          </button>

          <p className="mt-3 text-xs text-slate-500">
            The downloaded file contains the proof and public signals,
            not the original supply-chain values.
          </p>
        </div>
      )}
    </div>
  );
}

export default GenerateProof;