
import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import {
  getRecordByTransactionHash,
  generateZKPProof,
} from "../../services/api";
import {
  getWalletEncryptionPublicKey,
  decryptSalts,
} from "../../services/saltEncryption";
import { importSaltPackage } from "../../services/saltPackage";
import { submitZKPVerification } from "../../services/wallet";

function VerifyZKP() {
  const { user } = useAuth();

  const [transactionHash, setTransactionHash] = useState("");
  const [record, setRecord] = useState(null);
  const [values, setValues] = useState({});
  const [saltFile, setSaltFile] = useState(null);
  const [salts, setSalts] = useState(null);
  const [encryptionPublicKey, setEncryptionPublicKey] = useState("");
  const [proofResult, setProofResult] = useState(null);
  const [verificationResult, setVerificationResult] = useState(null);

  const [loadingRecord, setLoadingRecord] = useState(false);
  const [loadingSalts, setLoadingSalts] = useState(false);
  const [loadingProof, setLoadingProof] = useState(false);
  const [loadingVerification, setLoadingVerification] = useState(false);
  const [error, setError] = useState("");

  const getErrorMessage = (err) => {
    return (
      err.response?.data?.detail ||
      err.message ||
      "An unexpected error occurred."
    );
  };

  const requestEncryptionPublicKey = async () => {
    try {
      setError("");
      const publicKey = await getWalletEncryptionPublicKey(user.address);
      setEncryptionPublicKey(publicKey);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const retrieveRecord = async () => {
    try {
      setError("");
      setRecord(null);
      setValues({});
      setSalts(null);
      setSaltFile(null);
      setProofResult(null);
      setVerificationResult(null);
      setLoadingRecord(true);

      const response = await getRecordByTransactionHash(
        transactionHash.trim()
      );

      setRecord(response.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingRecord(false);
    }
  };

  const handleValueChange = (attribute, value) => {
    setValues((previous) => ({
      ...previous,
      [attribute]: value,
    }));
  };

  const importAndDecryptSalts = async () => {
    try {
      setError("");
      setSalts(null);
      setProofResult(null);
      setVerificationResult(null);

      if (!record) {
        throw new Error("Retrieve a supply-chain record first.");
      }

      if (!saltFile) {
        throw new Error("Please select the encrypted salt package.");
      }

      setLoadingSalts(true);

      const encryptedPackage = await importSaltPackage(saltFile);

      const decrypted = await decryptSalts(
        encryptedPackage,
        user.address,
        record.transaction_hash
      );

      const allowedNames = record.allowed_attributes.map(
        (attribute) => attribute.name
      );

      const receivedNames = Object.keys(decrypted.salts);

      if (
        allowedNames.length !== receivedNames.length ||
        !allowedNames.every((name) => receivedNames.includes(name))
      ) {
        throw new Error(
          "The salt package does not contain exactly the attributes permitted for your role."
        );
      }

      setSalts(decrypted.salts);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingSalts(false);
    }
  };

  const handleGenerateProof = async () => {
    try {
      setError("");
      setProofResult(null);
      setVerificationResult(null);

      if (!record) {
        throw new Error("Retrieve a supply-chain record first.");
      }

      if (!salts) {
        throw new Error("Import and decrypt the salt package first.");
      }

      const allowedNames = record.allowed_attributes.map(
        (attribute) => attribute.name
      );

      for (const attribute of allowedNames) {
        if (
          values[attribute] === undefined ||
          values[attribute].trim() === ""
        ) {
          throw new Error(`Please enter ${attribute.replaceAll("_", " ")}.`);
        }

        if (!salts[attribute]) {
          throw new Error(`Salt is missing for ${attribute}.`);
        }
      }

      setLoadingProof(true);

      const response = await generateZKPProof({
        transaction_hash: record.transaction_hash,
        values,
        salts,
      });

      setProofResult(response.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingProof(false);
    }
  };

  const handleBlockchainVerification = async () => {
    try {
      setError("");
      setVerificationResult(null);
      setLoadingVerification(true);

      if (!proofResult?.proof) {
        throw new Error("Generate a valid ZKP before verification.");
      }

      const result = await submitZKPVerification(
        user,
        record.record_id,
        proofResult.proof
      );

      setVerificationResult(result);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingVerification(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Verify Zero-Knowledge Proof
        </h1>

        <p className="mt-2 text-sm text-slate-600">
          Verify supply-chain information using a selective Groth16
          zero-knowledge proof.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">
          1. Stakeholder Encryption Public Key
        </h2>

        <p className="text-sm text-slate-600">
          Obtain your MetaMask encryption public key and securely share
          it with the Manufacturer so they can encrypt your permitted salts.
        </p>

        <button
          onClick={requestEncryptionPublicKey}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Get My Encryption Public Key
        </button>

        {encryptionPublicKey && (
          <div className="break-all rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            <p className="mb-2 font-semibold">Your Encryption Public Key</p>
            {encryptionPublicKey}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">
          2. Retrieve Supply-Chain Record
        </h2>

        <p className="text-sm text-slate-600">
          Enter the original blockchain transaction hash provided by
          the Manufacturer.
        </p>

        <input
          type="text"
          value={transactionHash}
          onChange={(event) => setTransactionHash(event.target.value)}
          placeholder="Enter storage transaction hash"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />

        <button
          onClick={retrieveRecord}
          disabled={loadingRecord || !transactionHash.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loadingRecord ? "Retrieving..." : "Retrieve Record"}
        </button>

        {record && (
          <div className="space-y-3 rounded-lg bg-slate-50 p-4 text-sm">
            <p>
              <strong>Record ID:</strong> {record.record_id}
            </p>

            <p className="break-all">
              <strong>Transaction Hash:</strong> {record.transaction_hash}
            </p>

            <p className="break-all">
              <strong>Manufacturer:</strong> {record.manufacturer}
            </p>

            <p>
              <strong>Your Role:</strong> {record.role_name}
            </p>

            <div>
              <strong>Permitted Attributes:</strong>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {record.allowed_attributes.map((attribute) => (
                  <li key={attribute.index}>
                    {attribute.name.replaceAll("_", " ")}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {record && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">
            3. Enter Reference Values
          </h2>

          <p className="text-sm text-slate-600">
            Enter your independently obtained reference values for all
            attributes permitted by your stakeholder role.
          </p>

          {record.allowed_attributes.map((attribute) => (
            <div key={attribute.index}>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                {attribute.name.replaceAll("_", " ")}
              </label>

              <input
                type="text"
                value={values[attribute.name] || ""}
                onChange={(event) =>
                  handleValueChange(attribute.name, event.target.value)
                }
                placeholder={`Enter ${attribute.name.replaceAll("_", " ")}`}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}

      {record && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">
            4. Import Encrypted Salt Package
          </h2>

          <p className="text-sm text-slate-600">
            Import the encrypted JSON package shared by the Manufacturer.
            MetaMask will request permission to decrypt it.
          </p>

          <input
            type="file"
            accept=".json,application/json"
            onChange={(event) => {
              setSaltFile(event.target.files?.[0] || null);
              setSalts(null);
              setProofResult(null);
              setVerificationResult(null);
            }}
            className="block w-full text-sm text-slate-600"
          />

          <button
            onClick={importAndDecryptSalts}
            disabled={loadingSalts || !saltFile}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingSalts ? "Decrypting..." : "Import and Decrypt Salts"}
          </button>

          {salts && (
            <p className="text-sm font-medium text-green-700">
              Encrypted salt package successfully decrypted and validated.
            </p>
          )}
        </div>
      )}

      {record && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">
            5. Generate Zero-Knowledge Proof
          </h2>

          <p className="text-sm text-slate-600">
            Generate and locally verify a Groth16 proof using your
            reference values, decrypted salts and on-chain commitments.
          </p>

          <button
            onClick={handleGenerateProof}
            disabled={loadingProof || !salts}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingProof ? "Generating Proof..." : "Generate ZKP"}
          </button>

          {proofResult && (
            <div className="rounded-lg bg-green-50 p-4 text-sm text-green-800 space-y-2">
              <p className="font-semibold">
                Zero-Knowledge Proof Generated Successfully
              </p>

              <p>
                Proof generation time:{" "}
                {proofResult.proof_generation_time_seconds} seconds
              </p>

              <p>
                Local proof verification time:{" "}
                {proofResult.proof_verification_time_seconds} seconds
              </p>
            </div>
          )}
        </div>
      )}

      {proofResult && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-slate-800">
            6. Verify on Blockchain
          </h2>

          <p className="text-sm text-slate-600">
            Submit the generated proof to the smart contract using
            your authenticated MetaMask wallet.
          </p>

          <button
            onClick={handleBlockchainVerification}
            disabled={loadingVerification}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingVerification
              ? "Waiting for Blockchain..."
              : "Verify on Blockchain"}
          </button>

          {verificationResult && (
            <div className="rounded-lg bg-green-50 p-4 text-sm text-green-800 space-y-2">
              <p className="font-semibold">
                Blockchain Verification Transaction Successful
              </p>

              <p>
                Block Number: {verificationResult.blockNumber}
              </p>

              <p>
                Gas Used: {verificationResult.gasUsed}
              </p>

              <p className="break-all">
                Transaction Hash: {verificationResult.transactionHash}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default VerifyZKP;
