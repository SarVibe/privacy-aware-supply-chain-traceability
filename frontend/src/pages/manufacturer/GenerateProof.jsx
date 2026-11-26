
import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { generateAttributeSalts } from "../../services/saltGenerator";
import { generateAttributeCommitments } from "../../services/commitment";
import { storeRecordOnChain } from "../../services/wallet";
import { encryptSalts } from "../../services/saltEncryption";
import { exportSaltPackage } from "../../services/saltPackage";

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

const ROLE_OPTIONS = [
  {
    value: "3",
    label: "Logistics Provider",
    attributes: [
      "product_id",
      "batch_number",
      "expiry_date",
      "shipment_id",
      "quantity",
      "source_location",
      "destination_location",
    ],
  },
  {
    value: "4",
    label: "Warehouse",
    attributes: ATTRIBUTES.map((item) => item.name),
  },
  {
    value: "5",
    label: "Distributor",
    attributes: ATTRIBUTES
      .filter((item) => item.name !== "quantity")
      .map((item) => item.name),
  },
  {
    value: "6",
    label: "Pharmacy",
    attributes: [
      "product_id",
      "product_name",
      "batch_number",
      "manufacturing_date",
      "expiry_date",
    ],
  },
];

function GenerateProof() {
  const { user } = useAuth();

  const [attributes, setAttributes] = useState({});
  const [salts, setSalts] = useState(null);
  const [record, setRecord] = useState(null);

  const [recipientAddress, setRecipientAddress] = useState("");
  const [recipientPublicKey, setRecipientPublicKey] = useState("");
  const [recipientRole, setRecipientRole] = useState("6");

  const [loading, setLoading] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedRole = ROLE_OPTIONS.find(
    (role) => role.value === recipientRole
  );

  const handleAttributeChange = (name, value) => {
    setAttributes((previous) => ({
      ...previous,
      [name]: value,
    }));
  };

  const handleStoreRecord = async (event) => {
    event.preventDefault();

    setLoading(true);
    setError("");
    setSuccess("");
    setRecord(null);
    setSalts(null);

    try {
      if (user?.role !== 2) {
        throw new Error("Only Manufacturers can register supply-chain records.");
      }

      const completeAttributes = {};

      for (const attribute of ATTRIBUTES) {
        const value = attributes[attribute.name]?.trim();

        if (!value) {
          throw new Error(`${attribute.label} is required.`);
        }

        completeAttributes[attribute.name] = value;
      }

      if (!/^\d{8}$/.test(completeAttributes.manufacturing_date)) {
        throw new Error("Manufacturing date must use YYYYMMDD format.");
      }

      if (!/^\d{8}$/.test(completeAttributes.expiry_date)) {
        throw new Error("Expiry date must use YYYYMMDD format.");
      }

      if (!/^\d+$/.test(completeAttributes.quantity)) {
        throw new Error("Quantity must be a non-negative integer.");
      }

      const generatedSalts = generateAttributeSalts();

      const commitments = await generateAttributeCommitments(
        completeAttributes,
        generatedSalts
      );

      const storageResult = await storeRecordOnChain(
        user,
        commitments
      );

      setSalts(generatedSalts);

      setRecord({
        transactionHash: storageResult.transactionHash,
        recordId: storageResult.recordId,
        blockNumber: storageResult.blockNumber,
        gasUsed: storageResult.gasUsed,
      });

      setSuccess("Supply-chain commitments stored successfully on-chain.");
    } catch (err) {
      setError(
        err.reason ||
          err.response?.data?.detail ||
          err.message ||
          "Unable to store the supply-chain record."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleShareSalts = async (event) => {
    event.preventDefault();

    setSharing(true);
    setError("");
    setSuccess("");

    try {
      if (!record || !salts) {
        throw new Error("Register a supply-chain record first.");
      }

      if (!recipientAddress.trim() || !recipientPublicKey.trim()) {
        throw new Error("Recipient wallet address and public key are required.");
      }

      const selectedSalts = Object.fromEntries(
        selectedRole.attributes.map((attribute) => [
          attribute,
          salts[attribute],
        ])
      );

      const encryptedPackage = await encryptSalts(
        recipientPublicKey.trim(),
        record.transactionHash,
        recipientAddress.trim(),
        selectedSalts
      );

      exportSaltPackage(
        encryptedPackage,
        record.transactionHash
      );

      setSuccess(
        `Encrypted salt package exported for ${selectedRole.label}.`
      );
    } catch (err) {
      setError(err.message || "Unable to encrypt the salt package.");
    } finally {
      setSharing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Register Supply-Chain Record
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Store salted Poseidon commitments on the blockchain and securely
          share authorized attribute salts with stakeholders.
        </p>
      </div>

      <form onSubmit={handleStoreRecord} className="space-y-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-800">
            Initial Supply-Chain Information
          </h2>

          <p className="mt-2 text-sm text-slate-500">
            Enter the initial values for all ten attributes. Only their
            cryptographic commitments will be stored on-chain.
          </p>

          <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
            {ATTRIBUTES.map((attribute) => (
              <div key={attribute.name}>
                <label className="mb-2 block text-sm font-medium text-slate-700">
                  {attribute.label}
                </label>

                <input
                  type="text"
                  required
                  value={attributes[attribute.name] || ""}
                  onChange={(event) =>
                    handleAttributeChange(
                      attribute.name,
                      event.target.value
                    )
                  }
                  placeholder={`Enter ${attribute.label.toLowerCase()}`}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>
            ))}
          </div>

          <p className="mt-5 text-xs text-slate-500">
            Dates must use YYYYMMDD format. Quantity must be a
            non-negative integer. String attributes support up to 62 UTF-8 bytes.
          </p>

          <button
            type="submit"
            disabled={loading || Boolean(record)}
            className="mt-6 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading
              ? "Waiting for MetaMask..."
              : record
                ? "Record Stored"
                : "Generate Commitments and Store"}
          </button>
        </div>
      </form>

      {record && (
        <div className="rounded-xl border border-green-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-800">
            Record Storage Successful
          </h2>

          <div className="mt-4 space-y-3 text-sm">
            <div>
              <p className="text-slate-500">Record ID</p>
              <p className="font-semibold text-slate-800">
                {record.recordId}
              </p>
            </div>

            <div>
              <p className="text-slate-500">Original Storage Transaction Hash</p>
              <p className="break-all font-mono text-xs text-slate-800">
                {record.transactionHash}
              </p>
            </div>

            <div>
              <p className="text-slate-500">Block Number</p>
              <p className="font-semibold text-slate-800">
                {record.blockNumber}
              </p>
            </div>

            <div>
              <p className="text-slate-500">Gas Used</p>
              <p className="font-semibold text-slate-800">
                {record.gasUsed}
              </p>
            </div>
          </div>

          <p className="mt-4 text-xs text-green-700">
            Ten attribute commitments have been stored. Raw values and
            random salts have not been submitted to the blockchain.
          </p>
        </div>
      )}

      {record && salts && (
        <form
          onSubmit={handleShareSalts}
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2 className="text-lg font-semibold text-slate-800">
            Securely Share Attribute Salts
          </h2>

          <p className="mt-2 text-sm text-slate-500">
            Enter the recipient's wallet address and encryption public key.
            The stakeholder must obtain their public key using their own MetaMask
            and share it with you securely.
          </p>

          <div className="mt-6 space-y-5">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">
                Stakeholder Role
              </label>

              <select
                value={recipientRole}
                onChange={(event) => setRecipientRole(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">
                Recipient Wallet Address
              </label>

              <input
                type="text"
                required
                value={recipientAddress}
                onChange={(event) => setRecipientAddress(event.target.value)}
                placeholder="0x..."
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700">
                Recipient Encryption Public Key
              </label>

              <textarea
                required
                rows={3}
                value={recipientPublicKey}
                onChange={(event) => setRecipientPublicKey(event.target.value)}
                placeholder="Paste the MetaMask encryption public key"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm font-medium text-slate-700">
                Attributes to be shared
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                {selectedRole.attributes.map((attribute) => (
                  <span
                    key={attribute}
                    className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-700"
                  >
                    {attribute}
                  </span>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={sharing}
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sharing
                ? "Encrypting..."
                : "Encrypt and Download Salt Package"}
            </button>
          </div>
        </form>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {success && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-700">
          {success}
        </div>
      )}
    </div>
  );
}

export default GenerateProof;
