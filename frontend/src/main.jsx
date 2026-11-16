import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  const [form, setForm] = React.useState({
    record_id: "",
    raw_description: "",
    stakeholder_org: "Generic_Org",
  });
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [serviceStatus, setServiceStatus] = React.useState("Checking...");
  const [ledgerStatus, setLedgerStatus] = React.useState("Checking...");

  React.useEffect(() => {
    async function loadStatus() {
      try {
        const healthResponse = await fetch("/health");
        if (!healthResponse.ok) {
          throw new Error("Backend unavailable");
        }
        setServiceStatus("Online");
      } catch {
        setServiceStatus("Unavailable");
      }

      try {
        const ledgerResponse = await fetch("/api/v1/ledger/summary");
        const payload = await ledgerResponse.json();
        if (!ledgerResponse.ok) {
          throw new Error(payload.detail || "Ledger unavailable");
        }
        setLedgerStatus(`${payload.total_records} records`);
      } catch {
        setLedgerStatus("Unavailable");
      }
    }

    loadStatus();
  }, []);

  function updateField(event) {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  }

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch("/api/v1/harmonize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "The backend rejected the request.");
      }
      setResult(payload);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Component 1</p>
        <h1>Supply-chain harmonization</h1>
        <p className="subtitle">
          Resolve heterogeneous product records before they are committed to the ledger.
        </p>
        <div className="status-row">
          <span>API: <strong>{serviceStatus}</strong></span>
          <span>Ledger: <strong>{ledgerStatus}</strong></span>
        </div>
      </section>

      <section className="card">
        <form onSubmit={submit}>
          <label>
            Record ID
            <input
              name="record_id"
              value={form.record_id}
              onChange={updateField}
              placeholder="REC_00001"
              required
            />
          </label>
          <label>
            Raw description
            <textarea
              name="raw_description"
              value={form.raw_description}
              onChange={updateField}
              placeholder="Didanosine 200mg tablets"
              rows="4"
              required
            />
          </label>
          <label>
            Stakeholder organization
            <input
              name="stakeholder_org"
              value={form.stakeholder_org}
              onChange={updateField}
              required
            />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? "Harmonizing..." : "Harmonize record"}
          </button>
        </form>

        {error && <p className="error">{error}</p>}
        {result && (
          <div className="result" aria-live="polite">
            <h2>Harmonization result</h2>
            <dl>
              <dt>Cluster</dt>
              <dd>{result.predicted_cluster_id}</dd>
              <dt>Similarity</dt>
              <dd>{result.similarity_score}</dd>
              <dt>New cluster</dt>
              <dd>{result.is_new_cluster ? "Yes" : "No"}</dd>
              <dt>Commitment</dt>
              <dd>{result.onchain_status}</dd>
              <dt>Transaction</dt>
              <dd>{result.tx_hash}</dd>
            </dl>
          </div>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
