
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function LandingPage() {
  const { login, loading } = useAuth();
  const navigate = useNavigate();

  const [error, setError] = useState("");

  const handleConnectWallet = async () => {
    try {
      setError("");

      await login();

      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Wallet connection failed.");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Navigation */}
      <header className="flex items-center justify-between px-8 py-6">
        <h1 className="text-2xl font-bold text-cyan-400">
          C3<span className="text-white"> ZKP</span>
        </h1>

        <span className="text-sm text-slate-400">
          Supply Chain Verification
        </span>
      </header>

      {/* Main content */}
      <main className="mx-auto flex min-h-[80vh] max-w-7xl flex-col items-center justify-center px-6 text-center">

        <div className="mb-6 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-5 py-2 text-sm text-cyan-300">
          Blockchain-Based Privacy-Aware Verification
        </div>

        <h2 className="max-w-4xl text-4xl font-bold leading-tight md:text-6xl">
          Secure Supply Chain
          <span className="block text-cyan-400">
            Verification with ZKP
          </span>
        </h2>

        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-400">
          Verify supply chain information securely using
          Zero-Knowledge Proofs and blockchain technology,
          without revealing sensitive product information.
        </p>

        {/* Wallet connection */}
        <button
          onClick={handleConnectWallet}
          disabled={loading}
          className="mt-10 rounded-xl bg-cyan-500 px-8 py-4 font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Connecting Wallet..." : "Connect MetaMask Wallet"}
        </button>

        {error && (
          <p className="mt-5 max-w-lg rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        <p className="mt-5 text-sm text-slate-500">
          Connect your registered stakeholder wallet to continue.
        </p>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 px-6 py-6 text-center text-sm text-slate-500">
        © 2026 C3 ZKP Supply Chain Verification System
      </footer>
    </div>
  );
}

export default LandingPage;
