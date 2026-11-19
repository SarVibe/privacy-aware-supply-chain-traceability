import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  JsonRpcProvider,
  toBeHex,
  zeroPadValue
} from "ethers";
import {
  CONTRACT_ADDRESS,
  EXPECTED_CHAIN_ID,
  getContract,
  ROLE_NAMES,
  shorten,
  STATUS_NAMES,
  isValidWalletAddress
} from "./contract.js";
import {
  calculateCommitment,
  createDiceSimilarity,
  DOSAGE_FORMS,
  formatPrice,
  productCircuitInput,
  productQgramHashes
} from "./product.js";
import {
  createProductProof,
  GROTH16_CIRCUIT_DOMAIN_SIZE,
  solidityProof
} from "./zkp.js";
import { CSV_HEADERS, parseProductsCsv } from "./csv.mjs";

const EMPTY_PRODUCT = {
  productName: "",
  manufacturerName: "",
  dosageForm: DOSAGE_FORMS[0],
  manufacturingDate: "",
  expiryDate: "",
  price: ""
};
const BATCH_SIZES = [2, 5, 10, 20, 50];
const MAX_CSV_ROWS = 6000;
const MAX_CSV_FILE_SIZE_BYTES = 10_000_000;
const MAX_PRODUCT_QGRAMS = 256;
const QGRAM_BLOCKS_PER_SCREEN_CALL = 16;

function bytes32(value) {
  return zeroPadValue(toBeHex(value), 32);
}

function minimumDiceOverlap(queryCount, thresholdPercent) {
  let minimumOverlap = Infinity;
  for (let candidateCount = 1; candidateCount <= MAX_PRODUCT_QGRAMS; candidateCount += 1) {
    const requiredOverlap = Math.ceil(
      thresholdPercent * (queryCount + candidateCount) / 200
    );
    if (requiredOverlap <= Math.min(queryCount, candidateCount)) {
      minimumOverlap = Math.min(minimumOverlap, requiredOverlap);
    }
  }
  return Number.isFinite(minimumOverlap) ? minimumOverlap : queryCount + 1;
}

function contiguousBlockRanges(blockNumbers) {
  if (blockNumbers.length === 0) return [];

  const ranges = [];
  let rangeStart = blockNumbers[0];
  let rangeEnd = rangeStart;
  for (const blockNumber of blockNumbers.slice(1)) {
    if (blockNumber === rangeEnd + 1) {
      rangeEnd = blockNumber;
      continue;
    }
    ranges.push([rangeStart, rangeEnd]);
    rangeStart = blockNumber;
    rangeEnd = blockNumber;
  }
  ranges.push([rangeStart, rangeEnd]);
  return ranges;
}

function errorMessage(error) {
  return error?.shortMessage || error?.reason || error?.message || "Unexpected error";
}

function startMemoryMonitor() {
  const getUsedHeapBytes = () => performance.memory?.usedJSHeapSize ?? null;
  const initialUsedHeapBytes = getUsedHeapBytes();
  let peakAdditionalHeapBytes = initialUsedHeapBytes === null ? null : 0;
  const interval = setInterval(() => {
    const usedHeapBytes = getUsedHeapBytes();
    if (usedHeapBytes !== null && initialUsedHeapBytes !== null) {
      peakAdditionalHeapBytes = Math.max(
        peakAdditionalHeapBytes ?? 0,
        usedHeapBytes - initialUsedHeapBytes
      );
    }
  }, 50);

  return () => {
    clearInterval(interval);
    const usedHeapBytes = getUsedHeapBytes();
    if (usedHeapBytes !== null && initialUsedHeapBytes !== null) {
      peakAdditionalHeapBytes = Math.max(
        peakAdditionalHeapBytes ?? 0,
        usedHeapBytes - initialUsedHeapBytes
      );
    }
    return peakAdditionalHeapBytes === null
      ? null
      : (peakAdditionalHeapBytes / (1024 * 1024)).toFixed(2);
  };
}

function logVerificationError(method, stage, error) {
  const rpcError = error?.info?.error || error?.error || error?.cause;
  console.error("[PharmaChain] Verification failed", {
    method,
    stage,
    code: error?.code,
    shortMessage: error?.shortMessage,
    reason: error?.reason,
    message: error?.message,
    rpcCode: rpcError?.code,
    rpcMessage: rpcError?.message,
    revertData: typeof error?.data === "string"
      ? error.data
      : typeof rpcError?.data === "string"
        ? rpcError.data
        : undefined,
    stack: error?.stack
  });
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The application request failed.");
  return result;
}

function formatTransaction(hash) {
  return hash ? `${hash.slice(0, 14)}...${hash.slice(-8)}` : "—";
}

function validateCsvProduct(product, rowNumber) {
  for (const field of ["manufacturingDate", "expiryDate"]) {
    const value = product[field];
    const date = /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? new Date(`${value}T00:00:00.000Z`)
      : null;
    if (!date || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
      throw new Error(`CSV row ${rowNumber}: ${field} must be a valid YYYY-MM-DD date.`);
    }
  }
  if (!DOSAGE_FORMS.includes(product.dosageForm)) {
    throw new Error(`CSV row ${rowNumber}: dosageForm must be ${DOSAGE_FORMS.join(", ")}.`);
  }
  try {
    productCircuitInput(product);
  } catch (error) {
    throw new Error(`CSV row ${rowNumber}: ${errorMessage(error)}`);
  }
}

function ProductFields({ value, onChange, includePrice = true }) {
  const update = (field) => (event) =>
    onChange((previous) => ({ ...previous, [field]: event.target.value }));

  return (
    <div className="form-grid">
      <label>
        Product name <small>1–31 UTF-8 bytes</small>
        <input
          required
          maxLength={31}
          value={value.productName}
          onChange={update("productName")}
          placeholder="e.g. Paracetamol"
        />
      </label>
      <label>
        Manufacturer name <small>1–31 UTF-8 bytes</small>
        <input
          required
          maxLength={31}
          value={value.manufacturerName}
          onChange={update("manufacturerName")}
          placeholder="e.g. Northstar Labs"
        />
      </label>
      <label>
        Dosage form
        <select value={value.dosageForm} onChange={update("dosageForm")}>
          {DOSAGE_FORMS.map((form) => (
            <option key={form}>{form}</option>
          ))}
        </select>
      </label>
      <label>
        Manufacturing date
        <input
          required
          type="date"
          value={value.manufacturingDate}
          onChange={update("manufacturingDate")}
        />
      </label>
      <label>
        Expiry date
        <input
          required
          type="date"
          value={value.expiryDate}
          onChange={update("expiryDate")}
        />
      </label>
      {includePrice && (
        <label>
          Price
          <input
            required
            inputMode="decimal"
            value={value.price}
            onChange={update("price")}
            placeholder="e.g. 12.50"
          />
        </label>
      )}
    </div>
  );
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="section-title modal-title">
          <h2 id="modal-title">{title}</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Close dialog">
            ×
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function App() {
  const provider = useMemo(
    () => new JsonRpcProvider("http://127.0.0.1:8546"),
    []
  );
  const [account, setAccount] = useState("");
  const [role, setRole] = useState(0);
  const [administrator, setAdministrator] = useState("");
  const [chainId, setChainId] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [configuredUsers, setConfiguredUsers] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeModal, setActiveModal] = useState("");
  const [product, setProduct] = useState(EMPTY_PRODUCT);
  const [csvFile, setCsvFile] = useState(null);
  const [recipient, setRecipient] = useState("");
  const [products, setProducts] = useState([]);
  const [verifyProduct, setVerifyProduct] = useState(EMPTY_PRODUCT);
  const [verification, setVerification] = useState(null);
  const [comparisonResults, setComparisonResults] = useState({});
  const [adminAddress, setAdminAddress] = useState("");
  const [adminRole, setAdminRole] = useState("1");
  const [fuzzyThreshold, setFuzzyThreshold] = useState(90);
  const [selectedFuzzyThreshold, setSelectedFuzzyThreshold] = useState("90");
  const [batchStatus, setBatchStatus] = useState({
    minimumTransactions: 10,
    allowedBatchSizes: BATCH_SIZES,
    pendingRegistrations: [],
    pendingCount: 0,
    remainingTransactions: 10,
    lastBlock: null,
    error: ""
  });
  const [selectedBatchSize, setSelectedBatchSize] = useState("10");
  const [batchError, setBatchError] = useState("");
  const [batchUpdating, setBatchUpdating] = useState(false);
  const registrationSubmittingRef = useRef(false);
  const csvInputRef = useRef(null);

  function recordVerification(result) {
    setVerification(result);
    const mode = result.method.includes("fuzzy q-gram")
      ? "fuzzy"
      : result.method === "Groth16-only"
        ? "groth16"
        : "bloom";
    setComparisonResults((previous) => ({ ...previous, [mode]: result }));
  }

  const contract = useMemo(() => {
    try {
      return getContract(provider);
    } catch {
      return null;
    }
  }, [provider]);

  const loadProducts = useCallback(async (activeContract = contract) => {
    if (!activeContract) return;
    const commitments = await activeContract.getProductCommitments();
    const records = await Promise.all(
      commitments.map(async (commitment) => {
        const record = await activeContract.getProduct(commitment);
        return {
          commitment,
          manufacturer: record.manufacturer,
          currentOwner: record.currentOwner,
          pendingDistributor: record.pendingDistributor,
          createdBlock: Number(record.createdBlock),
          bloomGroup: Number(record.bloomGroup),
          status: Number(record.status),
          exists: record.exists
        };
      })
    );
    setProducts(records.filter((record) => record.exists).reverse());
  }, [contract]);

  const applySession = useCallback(async (profile) => {
    setUsername(profile.username);
    setAccount(profile.address);
    setRole(profile.role);
    setAdministrator(profile.administrator);
    setChainId(BigInt(profile.chainId));
    if (contract) {
      const activeFuzzyThreshold = await contract.fuzzyThresholdPercent();
      setFuzzyThreshold(Number(activeFuzzyThreshold));
      setSelectedFuzzyThreshold(String(activeFuzzyThreshold));
      await loadProducts(contract);
    }
  }, [contract, loadProducts]);

  useEffect(() => {
    let active = true;
    const restoreSession = async () => {
      try {
        const response = await fetch("/api/auth/session");
        if (response.status === 401) return;
        const profile = await response.json();
        if (!response.ok) throw new Error(profile.error || "Could not restore login.");
        if (active) await applySession(profile);
      } catch (caught) {
        if (active) setError(errorMessage(caught));
      } finally {
        if (active) setAuthLoading(false);
      }
    };
    void restoreSession();
    return () => {
      active = false;
    };
  }, [applySession]);

  useEffect(() => {
    if (!account || !administrator || account.toLowerCase() !== administrator.toLowerCase()) {
      setConfiguredUsers([]);
      return;
    }
    let active = true;
    fetch("/api/admin/users")
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not read configured users.");
        if (active) setConfiguredUsers(result.users);
      })
      .catch((caught) => {
        if (active) setError(errorMessage(caught));
      });
    return () => {
      active = false;
    };
  }, [account, administrator]);

  const refreshBatchStatus = useCallback(async () => {
    const response = await fetch("/api/batching");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not read the batch-miner status.");
    setBatchStatus(result);
    setBatchError(result.error || "");
    return result;
  }, []);

  useEffect(() => {
    setSelectedBatchSize(String(batchStatus.minimumTransactions));
  }, [batchStatus.minimumTransactions]);

  useEffect(() => {
    let active = true;
    let timer;
    const refresh = async () => {
      try {
        await refreshBatchStatus();
      } catch (caught) {
        if (active) setBatchError(errorMessage(caught));
      } finally {
        if (active) timer = setTimeout(refresh, 500);
      }
    };
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [refreshBatchStatus]);

  useEffect(() => {
    if (!contract || !batchStatus.lastBlock?.hash) return;
    loadProducts().catch((caught) => setError(errorMessage(caught)));
  }, [batchStatus.lastBlock?.hash, contract, loadProducts]);

  async function signIn(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const profile = await postJson("/api/auth/login", { username, password });
      setPassword("");
      await applySession(profile);
      setNotice(`Signed in as ${profile.username}.`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setError("");
    try {
      await postJson("/api/auth/logout", {});
      setAccount("");
      setUsername("");
      setRole(0);
      setAdministrator("");
      setProducts([]);
      setNotice("Signed out.");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function runAction(operation, arguments_, successMessage) {
    if (!account) {
      setError("Sign in before submitting a transaction.");
      return null;
    }
    if (chainId !== EXPECTED_CHAIN_ID) {
      setError("The application is connected to the wrong blockchain network.");
      return null;
    }
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await postJson("/api/transactions", {
        operation,
        arguments: arguments_
      });
      if (result.pending) {
        setNotice("Transaction submitted and waiting in the local registration batch.");
      } else {
        setNotice(successMessage);
        if (operation !== "setFuzzyThresholdPercent") {
          if (contract) await loadProducts(contract);
          const response = await fetch("/api/auth/session");
          if (response.ok) await applySession(await response.json());
        }
      }
      return result;
    } catch (caught) {
      setError(errorMessage(caught));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function assignRole(event) {
    event.preventDefault();
    if (!isValidWalletAddress(adminAddress)) {
      setError("Enter a valid Ethereum wallet address.");
      return;
    }
    const result = await runAction(
      "setStakeholderRole",
      { stakeholder: adminAddress, role: Number(adminRole) },
      "Stakeholder role updated."
    );
    if (result) {
      setAdminAddress("");
      const response = await fetch("/api/admin/users");
      if (response.ok) setConfiguredUsers((await response.json()).users);
    }
  }

  async function applyFuzzyThreshold(event) {
    event.preventDefault();
    const threshold = Number(selectedFuzzyThreshold);
    if (!Number.isInteger(threshold) || threshold < 1 || threshold > 100) {
      setError("Dice threshold must be a whole percentage from 1 to 100.");
      return;
    }
    const result = await runAction(
      "setFuzzyThresholdPercent",
      { threshold },
      `Fuzzy Dice threshold set to ${threshold}%.`
    );
    if (result && !result.pending) {
      setFuzzyThreshold(threshold);
      setSelectedFuzzyThreshold(String(threshold));
    }
  }

  async function applyBatchSize(event) {
    event.preventDefault();
    setBatchUpdating(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/batching", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minimumTransactions: Number(selectedBatchSize) })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not update the batch size.");
      await refreshBatchStatus();
      setNotice(`Minimum transactions per block set to ${result.minimumTransactions}.`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBatchUpdating(false);
    }
  }

  async function registerProduct(event) {
    event.preventDefault();
    if (registrationSubmittingRef.current) return;
    registrationSubmittingRef.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (!contract || !account || chainId !== EXPECTED_CHAIN_ID) {
        throw new Error("Sign in to the local PharmaChain application before registering a product.");
      }
      const status = await refreshBatchStatus();
      if (status.error) throw new Error(status.error);
      const circuitInput = productCircuitInput(product);
      const commitment = await calculateCommitment(circuitInput);
      const digest = bytes32(commitment);
      const qgramHashes = productQgramHashes(product);
      const result = await postJson("/api/transactions", {
        operation: "registerProduct",
        arguments: { commitment: digest, qgramHashes }
      });
      setNotice(
        result.pending
          ? "Product registration submitted. It will remain pending until the batch threshold is reached."
          : "Product registration confirmed in the local chain."
      );
      if (!result.pending) await loadProducts(contract);
      setProduct(EMPTY_PRODUCT);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      registrationSubmittingRef.current = false;
      setBusy(false);
    }
  }

  async function registerProductsCsv(event) {
    event.preventDefault();
    if (registrationSubmittingRef.current) return;
    registrationSubmittingRef.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    let submittedCount = 0;
    try {
      if (!csvFile) throw new Error("Choose a CSV file first.");
      if (!contract || !account || chainId !== EXPECTED_CHAIN_ID) {
        throw new Error("Sign in to the local PharmaChain application before importing products.");
      }
      if (role !== 1) throw new Error("The connected wallet needs the Manufacturer role.");
      if (csvFile.size > MAX_CSV_FILE_SIZE_BYTES) {
        throw new Error("CSV file must be smaller than 10 MB.");
      }

      const contents = await csvFile.text();
      const rows = parseProductsCsv(contents);
      if (rows.length > MAX_CSV_ROWS) {
        throw new Error(`CSV is limited to ${MAX_CSV_ROWS.toLocaleString("en-US")} product rows per import.`);
      }
      const status = await refreshBatchStatus();
      if (status.error) throw new Error(status.error);
      const pendingCommitments = new Set(
        status.pendingRegistrations.map((item) => item.commitment.toLowerCase())
      );
      const registeredCommitments = new Set(
        Array.from(
          await contract.getProductCommitments(),
          (commitment) => commitment.toLowerCase()
        )
      );
      const prepared = [];
      const fileCommitments = new Set();
      for (const { rowNumber, product: csvProduct } of rows) {
        validateCsvProduct(csvProduct, rowNumber);
        const circuitInput = productCircuitInput(csvProduct);
        const commitment = await calculateCommitment(circuitInput);
        const digest = bytes32(commitment);
        const qgramHashes = productQgramHashes(csvProduct);
        const key = digest.toLowerCase();
        if (fileCommitments.has(key)) {
          throw new Error(`CSV row ${rowNumber}: this product duplicates another row's commitment.`);
        }
        if (pendingCommitments.has(key)) {
          throw new Error(`CSV row ${rowNumber}: this product is already pending registration.`);
        }
        if (registeredCommitments.has(key)) {
          throw new Error(`CSV row ${rowNumber}: this product is already registered.`);
        }
        fileCommitments.add(key);
        prepared.push({ digest, qgramHashes, rowNumber });
      }

      for (const item of prepared) {
        const result = await postJson("/api/transactions", {
          operation: "registerProduct",
          arguments: {
            commitment: item.digest,
            qgramHashes: item.qgramHashes
          }
        });
        submittedCount += 1;
        setNotice(
          result.pending
            ? `Submitted ${submittedCount} of ${prepared.length} CSV registration transactions. They remain pending until the batch threshold is reached.`
            : `Submitted ${submittedCount} of ${prepared.length} CSV registration transactions. The batch was confirmed in the local chain.`
        );
      }
      setCsvFile(null);
      if (csvInputRef.current) csvInputRef.current.value = "";
      await refreshBatchStatus();
      setNotice(`Submitted ${submittedCount} separate product-registration transactions from CSV. They will be mined when the batch threshold is reached.`);
    } catch (caught) {
      const message = errorMessage(caught);
      setError(
        submittedCount
          ? `Submitted ${submittedCount} CSV registration(s) before stopping. ${message}`
          : message
      );
    } finally {
      registrationSubmittingRef.current = false;
      setBusy(false);
    }
  }

  async function transferProduct(event, item) {
    event.preventDefault();
    if (!isValidWalletAddress(recipient)) {
      setError("Enter a valid distributor wallet address.");
      return;
    }
    const result = await runAction(
      "transferToDistributor",
      { commitment: item.commitment, distributor: recipient },
      "Shipment initiated. The selected distributor must accept it."
    );
    if (result) setRecipient("");
  }

  async function acceptShipment(item) {
    await runAction(
      "acceptShipment",
      { commitment: item.commitment },
      "Shipment accepted. The distributor is now recorded as the owner."
    );
  }

  async function verifyWithBloom() {
    setVerification(null);
    setError("");
    setBusy(true);
    const started = performance.now();
    const stopMemoryMonitor = startMemoryMonitor();
    let memoryMonitorStopped = false;
    let stage = "Preparing verification input";
    try {
      const inputPreparationStarted = performance.now();
      const input = productCircuitInput(verifyProduct);
      const commitment = await calculateCommitment(input);
      const digest = bytes32(commitment);
      const inputPreparationMs = performance.now() - inputPreparationStarted;
      stage = "Reading product commitment";
      const exactLookupStarted = performance.now();
      const record = await contract.getProduct(digest);
      const exactLookupMs = performance.now() - exactLookupStarted;
      if (!record.exists) {
        await runFuzzyMatching(
          verifyProduct,
          started,
          "Bloom-only",
          (nextStage) => { stage = nextStage; },
          { inputPreparationMs, exactLookupMs }
        );
        return;
      }
      const blockNumber = Number(record.createdBlock);
      const bloomGroup = Number(record.bloomGroup);
      stage = "Calling mightContain";
      const bloomScreeningStarted = performance.now();
      const rpcStarted = performance.now();
      const result = await contract.mightContain.staticCall(bloomGroup, digest);
      const rpcLatencyMs = (performance.now() - rpcStarted).toFixed(2);
      const bloomScreeningMs = (performance.now() - bloomScreeningStarted).toFixed(2);
      stage = "Estimating mightContain gas";
      const gasEstimateStarted = performance.now();
      const gasEstimate = await contract.mightContain.estimateGas(
        bloomGroup,
        digest,
        { from: account }
      );
      const gasEstimateMs = (performance.now() - gasEstimateStarted).toFixed(2);
      const elapsedMs = (performance.now() - started).toFixed(2);
      const peakJsHeapMb = stopMemoryMonitor();
      memoryMonitorStopped = true;
      recordVerification({
        method: "Bloom-only",
        valid: result,
        bloomScreeningMs,
        rpcLatencyMs,
        gasEstimate: gasEstimate.toString(),
        gasEstimateMs,
        elapsedMs,
        peakJsHeapMb,
        zkpVerificationCount: 0,
        note: result
          ? `Possible Bloom match in group ${bloomGroup} only. This is not exact verification and can be a false positive.`
          : `No match in Bloom filter group ${bloomGroup}.`,
        blockNumber,
        bloomGroup
      });
    } catch (caught) {
      logVerificationError("Bloom-only", stage, caught);
      setError(errorMessage(caught));
    } finally {
      if (!memoryMonitorStopped) stopMemoryMonitor();
      setBusy(false);
    }
  }

  async function runFuzzyMatching(
    product,
    started,
    source = "Bloom-only",
    setStage = () => {},
    initialTimings = {}
  ) {
    const stopMemoryMonitor = startMemoryMonitor();
    let memoryMonitorStopped = false;
    try {
      const queryHashingStarted = performance.now();
      const queryHashes = productQgramHashes(product);
      const queryHashingMs = performance.now() - queryHashingStarted;
      if (queryHashes.length === 0) {
        throw new Error("The entered product details do not produce any character trigrams.");
      }

      setStage("Reading fuzzy match threshold");
      const thresholdReadStarted = performance.now();
      const activeThreshold = Number(await contract.fuzzyThresholdPercent());
      const thresholdReadMs = performance.now() - thresholdReadStarted;
      setFuzzyThreshold(activeThreshold);
      setSelectedFuzzyThreshold(String(activeThreshold));
      setStage("Screening q-gram Bloom blocks");
      const minimumOverlap = minimumDiceOverlap(queryHashes.length, activeThreshold);
      const bloomScreeningStarted = performance.now();
      const candidateBlocks = [];
      let totalBlockCount = 0;
      for (
        let firstBlockIndex = 0;
        firstBlockIndex === 0 || firstBlockIndex < totalBlockCount;
        firstBlockIndex += QGRAM_BLOCKS_PER_SCREEN_CALL
      ) {
        const screening = await contract.getQgramCandidateBlocks(
          queryHashes,
          minimumOverlap,
          firstBlockIndex,
          QGRAM_BLOCKS_PER_SCREEN_CALL
        );
        totalBlockCount = Number(screening.totalBlocks);
        candidateBlocks.push(
          ...Array.from(screening.candidateBlocks, (blockNumber) => Number(blockNumber))
        );
      }
      const bloomScreeningMs = performance.now() - bloomScreeningStarted;
      const blockComparisonCount = totalBlockCount * queryHashes.length;

      setStage("Reading q-gram records from candidate blocks");
      const eventRetrievalStarted = performance.now();
      const eventFilter = contract.filters.ProductQgrams(null, null, null);
      const events = [];
      for (const [fromBlock, toBlock] of contiguousBlockRanges(candidateBlocks)) {
        events.push(
          ...await contract.queryFilter(eventFilter, fromBlock, toBlock)
        );
      }
      const eventRetrievalMs = performance.now() - eventRetrievalStarted;

      const diceStarted = performance.now();
      const scoreDice = createDiceSimilarity(queryHashes);
      const scoredProducts = events.map((event) => ({
        commitment: event.args.commitment,
        bloomGroup: Number(event.args.bloomGroup),
        score: scoreDice(event.args.qgramHashes)
      }));
      const candidateQgramCount = events.reduce(
        (total, event) => total + event.args.qgramHashes.length,
        0
      );
      const diceScoringMs = performance.now() - diceStarted;
      const queryComparisonCount = queryHashes.length * events.length;
      const rankingTerm = events.length > 1
        ? Math.round(events.length * Math.log2(events.length))
        : 0;
      const rankingStarted = performance.now();
      scoredProducts.sort((left, right) => right.score - left.score);
      const matches = scoredProducts.filter(
        (item) => item.score * 100 >= activeThreshold
      );
      const rankingMs = performance.now() - rankingStarted;
      const formatComplexityTerm = (value) => value.toLocaleString("en-US");
      const complexityTerms = [
        queryHashes.length,
        blockComparisonCount,
        candidateQgramCount,
        queryComparisonCount,
        rankingTerm
      ];
      const complexitySum = complexityTerms.reduce((total, term) => total + term, 0);
      const complexityValue = `O(${complexityTerms.map(formatComplexityTerm).join(" + ")}) = O(${formatComplexityTerm(complexitySum)})`;
      const displayedProducts = (matches.length ? matches : scoredProducts.slice(0, 5))
        .slice(0, 10);

      setStage("Reading fuzzy candidate product details");
      const productDetailsStarted = performance.now();
      const fuzzyMatches = await Promise.all(displayedProducts.map(async (item) => {
        const record = await contract.getProduct(item.commitment);
        return {
          ...item,
          manufacturer: record.manufacturer,
          blockNumber: Number(record.createdBlock),
          matchesThreshold: item.score * 100 >= activeThreshold
        };
      }));
      const productDetailsMs = performance.now() - productDetailsStarted;
      const elapsedMs = (performance.now() - started).toFixed(2);
      const measuredStageTotal = Object.values({
        ...initialTimings,
        queryHashingMs,
        thresholdReadMs,
        bloomScreeningMs,
        eventRetrievalMs,
        diceScoringMs,
        rankingMs,
        productDetailsMs
      }).reduce((total, duration) => total + duration, 0);
      const otherProcessingMs = Math.max(
        0,
        performance.now() - started - measuredStageTotal
      );
      const peakJsHeapMb = stopMemoryMonitor();
      memoryMonitorStopped = true;

      recordVerification({
        method: `${source} fuzzy q-gram`,
        valid: matches.length > 0,
        elapsedMs,
        ...Object.fromEntries(
          Object.entries({
            ...initialTimings,
            queryHashingMs,
            thresholdReadMs,
            bloomScreeningMs,
            eventRetrievalMs,
            diceScoringMs,
            rankingMs,
            productDetailsMs,
            otherProcessingMs
          }).map(([name, duration]) => [name, duration.toFixed(2)])
        ),
        queryQgramCount: queryHashes.length,
        totalBlockCount,
        candidateBlockCount: candidateBlocks.length,
        blockComparisonCount,
        candidateQgramCount,
        queryComparisonCount,
        rankingTerm,
        complexitySum,
        complexityValue,
        peakJsHeapMb,
        zkpVerificationCount: 0,
        fuzzyThreshold: activeThreshold,
        scoredProductCount: events.length,
        registeredProductCount: products.length,
        thresholdMatchCount: matches.length,
        fuzzyMatches,
        note: matches.length
          ? `${matches.length} product candidate(s) met the ${activeThreshold}% Dice threshold. The q-gram Bloom filter passed ${candidateBlocks.length} of ${totalBlockCount} blocks; Dice was calculated only for products registered in those blocks.`
          : scoredProducts.length
            ? `No product met the ${activeThreshold}% Dice threshold. The q-gram Bloom filter passed ${candidateBlocks.length} of ${totalBlockCount} blocks; closest products in those blocks are shown for reference.`
            : totalBlockCount && candidateBlocks.length === 0
              ? `No q-gram Bloom blocks passed the safe screening threshold, so no product records were Dice-scored.`
              : candidateBlocks.length
                ? "Blocks passed q-gram Bloom screening, but they contain no q-gram events to score. Products registered without q-gram data cannot be searched fuzzily."
                : "No product q-gram records were found. Older registrations without q-gram data cannot be searched fuzzily."
      });
    } finally {
      if (!memoryMonitorStopped) stopMemoryMonitor();
    }
  }

  async function verifyWithGroth16() {
    setVerification(null);
    setError("");
    setBusy(true);
    const started = performance.now();
    const stopMemoryMonitor = startMemoryMonitor();
    let memoryMonitorStopped = false;
    let stage = "Preparing proof input";
    try {
      const input = productCircuitInput(verifyProduct);
      const commitment = await calculateCommitment(input);
      const digest = bytes32(commitment);
      stage = "Reading product commitment";
      const record = await contract.getProduct(digest);
      if (!record.exists) {
        throw new Error("No registered product matches the details entered.");
      }
      const blockNumber = Number(record.createdBlock);
      const bloomGroup = Number(record.bloomGroup);
      stage = "Generating Groth16 proof";
      const proofStarted = performance.now();
      const generated = await createProductProof(input);
      const proofTimeMs = performance.now() - proofStarted;
      if (BigInt(generated.commitment) !== BigInt(commitment)) {
        throw new Error("Proof circuit commitment did not match the locally computed commitment.");
      }
      const solidity = solidityProof(generated.proof);
      const publicSignals = [BigInt(generated.publicSignals[0])];
      stage = "Calling verifyProof";
      const rpcStarted = performance.now();
      const valid = await contract.verifyProof.staticCall(
        digest,
        solidity.a,
        solidity.b,
        solidity.c,
        publicSignals
      );
      const rpcLatencyMs = (performance.now() - rpcStarted).toFixed(2);
      const zkpVerificationMs = rpcLatencyMs;
      stage = "Estimating verifyProof gas";
      const gasEstimateStarted = performance.now();
      const gasEstimate = await contract.verifyProof.estimateGas(
        digest,
        solidity.a,
        solidity.b,
        solidity.c,
        publicSignals,
        { from: account }
      );
      const gasEstimateMs = (performance.now() - gasEstimateStarted).toFixed(2);
      const elapsedMs = (performance.now() - started).toFixed(2);
      const peakJsHeapMb = stopMemoryMonitor();
      memoryMonitorStopped = true;
      const proverGrowthTerm = Math.round(
        GROTH16_CIRCUIT_DOMAIN_SIZE * Math.log2(GROTH16_CIRCUIT_DOMAIN_SIZE)
      );
      recordVerification({
        method: "Groth16-only",
        valid,
        blockNumber,
        bloomGroup,
        proofTimeMs: proofTimeMs.toFixed(2),
        zkpVerificationMs,
        rpcLatencyMs,
        gasEstimate: gasEstimate.toString(),
        gasEstimateMs,
        elapsedMs,
        peakJsHeapMb,
        publicInputCount: publicSignals.length,
        complexityValue: `Prover O(${GROTH16_CIRCUIT_DOMAIN_SIZE.toLocaleString("en-US")} × log₂ ${GROTH16_CIRCUIT_DOMAIN_SIZE.toLocaleString("en-US")}) = O(${proverGrowthTerm.toLocaleString("en-US")}); verifier O(${publicSignals.length})`,
        zkpVerificationCount: 1,
        note: valid
          ? "The proof that the entered private fields match the commitment verified."
          : "No registered product or the proof did not match."
      });
    } catch (caught) {
      logVerificationError("Groth16-only", stage, caught);
      setError(errorMessage(caught));
    } finally {
      if (!memoryMonitorStopped) stopMemoryMonitor();
      setBusy(false);
    }
  }

  const isOwner = administrator && account.toLowerCase() === administrator.toLowerCase();
  const isRightNetwork = chainId === EXPECTED_CHAIN_ID;
  const received = products.filter(
    (item) => item.pendingDistributor.toLowerCase() === account.toLowerCase()
  );
  const owned = products.filter(
    (item) => item.currentOwner.toLowerCase() === account.toLowerCase()
  );

  return (
    <main className="page-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">Medicine custody research prototype</span>
          <h1>PharmaChain <span>Research</span></h1>
          <p>Local authenticated accounts · Manufacturer → Distributor · Commitments + Groth16</p>
        </div>
        {account && (
          <div className="account-session">
            <span>{username} · {shorten(account)}</span>
            <button className="secondary" onClick={signOut} disabled={busy}>Sign out</button>
          </div>
        )}
      </header>

      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner success">{notice}</div>}
      {!account && !authLoading && (
        <section className="panel auth-panel">
          <div className="section-title">
            <div><span className="step">LOGIN</span><h2>Sign in to PharmaChain</h2></div>
            <span className="muted">Local configured account</span>
          </div>
          <form className="inline-form" onSubmit={signIn}>
            <label>
              Username
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </section>
      )}
      {account && !contract && (
        <div className="banner error">No deployed contract address found. Follow the setup/deploy steps in README.</div>
      )}
      {account && contract && !isRightNetwork && (
        <div className="banner error">Wrong network. Connect to the PharmaChain Python local chain.</div>
      )}

      {isOwner && contract && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step">ADMIN</span><h2>Assign stakeholder roles</h2></div>
            <span className="muted">Contract deployer only</span>
          </div>
          <form className="inline-form" onSubmit={assignRole}>
            <label>
              Configured account
              <select
                value={adminAddress}
                onChange={(event) => setAdminAddress(event.target.value)}
                required
              >
                <option value="">Select a configured user</option>
                {configuredUsers.map((user) => (
                  <option key={user.address} value={user.address}>
                    {user.username} · {shorten(user.address)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Role
              <select value={adminRole} onChange={(event) => setAdminRole(event.target.value)}>
                <option value="1">Manufacturer</option>
                <option value="2">Distributor</option>
                <option value="0">Remove role</option>
              </select>
            </label>
            <button className="secondary" disabled={busy}>Set role</button>
          </form>
        </section>
      )}

      {account && contract && (isOwner || role === 1 || role === 2) && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step">FUZZY SEARCH</span><h2>Fuzzy match threshold</h2></div>
            <span className="muted">Shared setting · current threshold {fuzzyThreshold}%</span>
          </div>
          <p className="muted">
            The administrator, manufacturer, or distributor can update this threshold. It applies to fuzzy matching for everyone.
          </p>
          <form className="inline-form" onSubmit={applyFuzzyThreshold}>
            <label>
              Minimum Dice similarity (%)
              <input
                type="number"
                min="1"
                max="100"
                step="1"
                value={selectedFuzzyThreshold}
                onChange={(event) => setSelectedFuzzyThreshold(event.target.value)}
              />
            </label>
            <button className="secondary" disabled={busy}>Apply threshold</button>
          </form>
        </section>
      )}

      {account && contract && (
        <section className="panel shortcut-panel">
          <div className="section-title">
            <div><span className="step">TOOLS</span><h2>Supply-chain management</h2></div>
          </div>
          <div className="shortcut-actions">
            {isOwner && (
              <button className="secondary" onClick={() => setActiveModal("batching")}>
                Block batching configuration
              </button>
            )}
            <button className="secondary" onClick={() => setActiveModal("ledger")}>
              On-chain product records
            </button>
            {role === 1 && (
              <button className="secondary" onClick={() => setActiveModal("transfer")}>
                Send a product to a distributor
              </button>
            )}
            {role === 1 && (
              <button className="secondary" onClick={() => setActiveModal("csv")}>
                Register products from CSV
              </button>
            )}
          </div>
        </section>
      )}

      {role === 1 && contract && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step">01</span><h2>Manufacturer: register product</h2></div>
            <span className="role-pill manufacturer">Manufacturer</span>
          </div>
          <form onSubmit={registerProduct}>
            <ProductFields value={product} onChange={setProduct} />
            <div className="actions">
              <button className="primary" disabled={busy}>
                {busy ? "Submitting…" : "Commit product on-chain"}
              </button>
              <span className="muted">The transaction contains only the commitment.</span>
            </div>
          </form>
        </section>
      )}

      {role === 2 && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step">01</span><h2>Distributor: incoming shipments</h2></div>
            <span className="role-pill distributor">Distributor</span>
          </div>
          {received.length === 0 ? (
            <p className="muted">No shipments are currently waiting for this wallet.</p>
          ) : received.map((item) => (
            <div className="product-row" key={item.commitment}>
              <div>
                <strong>{shorten(item.commitment)}</strong>
                <small>From {shorten(item.manufacturer)} · block {item.createdBlock}</small>
              </div>
              <button className="primary" disabled={busy} onClick={() => acceptShipment(item)}>
                Accept shipment
              </button>
            </div>
          ))}
          <h3 className="subheading">Accepted product commitments</h3>
          {owned.filter((item) => item.status === 2).map((item) => (
            <div className="product-row compact" key={item.commitment}>
              <code>{item.commitment}</code>
              <small>Received in block {item.createdBlock}</small>
            </div>
          ))}
        </section>
      )}

      {account && contract && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step">VERIFY</span><h2>Verify the complete product details</h2></div>
            <span className="muted">Details are processed locally</span>
          </div>
          <p className="muted">
            Bloom-only checks the exact commitment with its group Bloom filter. If the
            commitment is absent, the block-level q-gram Bloom filter screens mined
            blocks, then fuzzy matching applies Dice similarity only to products in blocks
            that pass. Groth16-only generates a proof in the browser and verifies it
            against the on-chain commitment. Exact Bloom groups of 10 registrations are
            separate from Ethereum block numbers.
          </p>
          <ProductFields value={verifyProduct} onChange={setVerifyProduct} />
          <div className="verify-actions">
            <button className="secondary" disabled={busy} onClick={verifyWithBloom}>Bloom-only</button>
            <button className="secondary" disabled={busy} onClick={verifyWithGroth16}>Groth16-only</button>
          </div>
          {verification && (
            <div className={`result-card ${verification.valid ? "valid" : "invalid"}`}>
              <strong>
                {verification.method.includes("fuzzy q-gram")
                  ? verification.valid
                    ? "FUZZY CANDIDATE(S) FOUND"
                    : "NO FUZZY CANDIDATE MET THE THRESHOLD"
                  : `${verification.method}: ${verification.valid ? "MATCH" : "NO MATCH"}`}
              </strong>
              <p>{verification.note}</p>
              {verification.blockNumber !== undefined && (
                <small>Registration block: {verification.blockNumber} · Bloom group: {verification.bloomGroup}</small>
              )}
              {verification.method.includes("fuzzy q-gram") && (
                <>
                  <small>
                    Overall verification time: {verification.elapsedMs} ms
                  </small>
                      <small>Product input and commitment preparation: {verification.inputPreparationMs} ms</small>
                      <small>Exact commitment lookup: {verification.exactLookupMs} ms</small>
                      <small>Query q-gram generation: {verification.queryHashingMs} ms</small>
                      <small>Read configured Dice threshold: {verification.thresholdReadMs} ms</small>
                      <small>
                        Q-gram Bloom screening: {verification.bloomScreeningMs} ms ·{" "}
                        {verification.candidateBlockCount} / {verification.totalBlockCount} blocks passed
                      </small>
                      <small>Retrieve q-gram events for passing blocks: {verification.eventRetrievalMs} ms</small>
                      <small>Dice computation: {verification.diceScoringMs} ms</small>
                      <small>Sort scores and apply threshold: {verification.rankingMs} ms</small>
                      <small>Load details for displayed products: {verification.productDetailsMs} ms</small>
                      <small>Other processing / overhead: {verification.otherProcessingMs} ms</small>
                  <small>
                    Products Dice-scored / registered / threshold matches:{" "}
                    {verification.scoredProductCount} / {verification.registeredProductCount} / {verification.thresholdMatchCount}
                  </small>
                  <small>
                    Sampled additional memory: {verification.peakJsHeapMb === null
                      ? "not available"
                      : `${verification.peakJsHeapMb} MB*`}
                  </small>
                  <small>
                    <span title="Substitutes Q + BQ + Σqᵢ + NQ + N log₂N. These are asymptotic growth-term values, not measured CPU instruction counts; RPC retrieval is excluded.">
                      Complexity (numeric terms):{" "}
                      <code>{verification.complexityValue}</code>
                    </span>
                  </small>
                  {verification.fuzzyMatches.length > 0 && (
                    <div className="table-scroll">
                      <table>
                        <thead><tr><th>Dice similarity</th><th>Commitment</th><th>Manufacturer</th><th>Registration block</th><th>10-product group</th><th>Threshold</th></tr></thead>
                        <tbody>{verification.fuzzyMatches.map((item) => (
                          <tr key={item.commitment}>
                            <td>{(item.score * 100).toFixed(2)}%</td>
                            <td><code>{shorten(item.commitment)}</code></td>
                            <td>{shorten(item.manufacturer)}</td>
                            <td>{item.blockNumber}</td>
                            <td>{item.bloomGroup}</td>
                            <td>{item.matchesThreshold ? "Met" : "Not met"}</td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                  )}
                  <small>Fuzzy similarity is a candidate search, not proof that product details are identical.</small>
                </>
              )}
              {verification.method === "Bloom-only" && (
                <>
                  <small>Overall verification time: {verification.elapsedMs} ms</small>
                  <small>Bloom screening time: {verification.bloomScreeningMs} ms</small>
                  <small>Hash operations: 3</small>
                  <small>Estimated gas for Bloom check: {verification.gasEstimate}</small>
                  <small>
                    Sampled additional memory: {verification.peakJsHeapMb === null
                      ? "not available"
                      : `${verification.peakJsHeapMb} MB*`}
                  </small>
                  <small>Complexity: <code>O(3)</code> (three Bloom hash probes).</small>
                </>
              )}
              {verification.method === "Groth16-only" && (
                <>
                  <small>Overall verification time: {verification.elapsedMs} ms</small>
                  <small>Proof generation: {verification.proofTimeMs} ms</small>
                  <small>Proof verification: {verification.zkpVerificationMs} ms</small>
                  <small>Estimated gas: {verification.gasEstimate}</small>
                  <small>
                    Sampled additional memory: {verification.peakJsHeapMb === null
                      ? "not available"
                      : `${verification.peakJsHeapMb} MB*`}
                  </small>
                  <small>
                    Complexity (fixed circuit): <code>{verification.complexityValue}</code>
                    {" "}growth terms; not measured operation counts.
                  </small>
                </>
              )}
            </div>
          )}
          {Object.keys(comparisonResults).length > 0 && (
            <div className="result-card">
              <strong>Computational efficiency comparison</strong>
              <small>
                Latest completed run for each method in this page session. Memory is sampled
                additional JavaScript heap; 0.00 MB means no additional heap was detected,
                not zero actual memory.
              </small>
              <small>On-chain gas values are read-only execution estimates in gas units, not transaction fees; fuzzy scanning is off-chain.</small>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Fuzzy q-gram + Dice</th>
                      <th>Exact Bloom</th>
                      <th>Groth16</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Overall verification time</td>
                      <td>{comparisonResults.fuzzy ? `${comparisonResults.fuzzy.elapsedMs} ms` : "N/A"}</td>
                      <td>{comparisonResults.bloom ? `${comparisonResults.bloom.elapsedMs} ms` : "N/A"}</td>
                      <td>{comparisonResults.groth16 ? `${comparisonResults.groth16.elapsedMs} ms` : "N/A"}</td>
                    </tr>
                    <tr>
                      <td>Bloom screening</td>
                      <td>{comparisonResults.fuzzy
                        ? `${comparisonResults.fuzzy.bloomScreeningMs} ms (${comparisonResults.fuzzy.candidateBlockCount} / ${comparisonResults.fuzzy.totalBlockCount} blocks passed)`
                        : "N/A"}</td>
                      <td>{comparisonResults.bloom ? `${comparisonResults.bloom.bloomScreeningMs} ms` : "N/A"}</td>
                      <td>N/A</td>
                    </tr>
                    <tr>
                      <td>Dice computation</td>
                      <td>{comparisonResults.fuzzy ? `${comparisonResults.fuzzy.diceScoringMs} ms` : "N/A"}</td>
                      <td>N/A</td>
                      <td>N/A</td>
                    </tr>
                    <tr>
                      <td>Products scored / registered / matches</td>
                      <td>{comparisonResults.fuzzy
                        ? `${comparisonResults.fuzzy.scoredProductCount} / ${comparisonResults.fuzzy.registeredProductCount} / ${comparisonResults.fuzzy.thresholdMatchCount}`
                        : "N/A"}</td>
                      <td>N/A</td>
                      <td>N/A</td>
                    </tr>
                    <tr>
                      <td>Proof generation</td>
                      <td>N/A</td>
                      <td>N/A</td>
                      <td>{comparisonResults.groth16 ? `${comparisonResults.groth16.proofTimeMs} ms` : "N/A"}</td>
                    </tr>
                    <tr>
                      <td>Proof verification</td>
                      <td>N/A</td>
                      <td>N/A</td>
                      <td>{comparisonResults.groth16 ? `${comparisonResults.groth16.zkpVerificationMs} ms` : "N/A"}</td>
                    </tr>
                    <tr>
                      <td>Estimated execution gas</td>
                      <td>N/A (off-chain scan)</td>
                      <td>{comparisonResults.bloom?.gasEstimate ?? "N/A"}</td>
                      <td>{comparisonResults.groth16?.gasEstimate ?? "N/A"}</td>
                    </tr>
                    <tr>
                      <td>Sampled additional memory</td>
                      <td>{comparisonResults.fuzzy?.peakJsHeapMb === undefined
                        ? "N/A"
                        : comparisonResults.fuzzy.peakJsHeapMb === null
                          ? "Unavailable"
                          : `${comparisonResults.fuzzy.peakJsHeapMb} MB`}</td>
                      <td>{comparisonResults.bloom?.peakJsHeapMb === undefined
                        ? "N/A"
                        : comparisonResults.bloom.peakJsHeapMb === null
                          ? "Unavailable"
                          : `${comparisonResults.bloom.peakJsHeapMb} MB`}</td>
                      <td>{comparisonResults.groth16?.peakJsHeapMb === undefined
                        ? "N/A"
                        : comparisonResults.groth16.peakJsHeapMb === null
                          ? "Unavailable"
                          : `${comparisonResults.groth16.peakJsHeapMb} MB`}</td>
                    </tr>
                    <tr>
                      <td>Complexity</td>
                      <td>{comparisonResults.fuzzy
                        ? <code title="Substitutes Q + BQ + Σqᵢ + NQ + N log₂N; these are growth terms, not measured instructions.">{comparisonResults.fuzzy.complexityValue}</code>
                        : "N/A"}</td>
                      <td><code>O(3)</code></td>
                      <td>{comparisonResults.groth16
                        ? <code title="Uses the proving-key domain size (2,048) and public-input count from this run; growth terms, not measured operation counts.">{comparisonResults.groth16.complexityValue}</code>
                        : "N/A"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              {comparisonResults.fuzzy && (
                <div className="complexity-explanation">
                          <small>
                            <strong>Fuzzy complexity calculation (latest run)</strong>
                          </small>
                          <small>
                            Q = {comparisonResults.fuzzy.queryQgramCount.toLocaleString("en-US")} unique q-grams in the query.
                          </small>
                          <small>
                            B = {comparisonResults.fuzzy.totalBlockCount.toLocaleString("en-US")} blockchain blocks screened; {comparisonResults.fuzzy.candidateBlockCount.toLocaleString("en-US")} passed the q-gram Bloom filter.
                          </small>
                          <small>
                            BQ = B × Q = {comparisonResults.fuzzy.totalBlockCount.toLocaleString("en-US")} × {comparisonResults.fuzzy.queryQgramCount.toLocaleString("en-US")} = {comparisonResults.fuzzy.blockComparisonCount.toLocaleString("en-US")} maximum q-gram Bloom membership checks.
                          </small>
                          <small>
                            Σqᵢ = {comparisonResults.fuzzy.candidateQgramCount.toLocaleString("en-US")} total unique q-grams across candidate records.
                          </small>
                          <small>
                            N = {comparisonResults.fuzzy.scoredProductCount.toLocaleString("en-US")} candidate records scored.
                          </small>
                          <small>
                            NQ = N × Q = {comparisonResults.fuzzy.scoredProductCount.toLocaleString("en-US")} × {comparisonResults.fuzzy.queryQgramCount.toLocaleString("en-US")} = {comparisonResults.fuzzy.queryComparisonCount.toLocaleString("en-US")} query-to-candidate comparisons.
                          </small>
                          <small>
                            N log₂N = {comparisonResults.fuzzy.scoredProductCount.toLocaleString("en-US")} × log₂({comparisonResults.fuzzy.scoredProductCount.toLocaleString("en-US")}) ≈ {comparisonResults.fuzzy.rankingTerm.toLocaleString("en-US")} ranking-term units (rounded; 0 when N ≤ 1).
                          </small>
                          <small>
                            Q + BQ + Σqᵢ + NQ + N log₂N = {comparisonResults.fuzzy.complexitySum.toLocaleString("en-US")} total growth-term units.
                          </small>
                          <small>
                            These are illustrative complexity terms; RPC event retrieval is excluded. Bloom screening uses a conservative overlap bound derived from the Dice threshold and the 256-q-gram per-product limit, so a product meeting the threshold is not screened out.
                          </small>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {account && role === 0 && !isOwner && contract && (
        <div className="banner info">
          This wallet has no stakeholder role. Ask the contract administrator at {shorten(administrator)} to assign Manufacturer or Distributor.
        </div>
      )}

      <footer>
        <span>Role: {ROLE_NAMES[role] || "Unknown"}</span>
        <span>Groth16 · Circom · Poseidon · 2048-bit Bloom groups (10 products each)</span>
      </footer>

      {activeModal === "batching" && (
        <Modal title="Block batching configuration" onClose={() => setActiveModal("")}>
          <p className="muted">Python local EVM · no time-based mining</p>
          <form className="inline-form modal-form" onSubmit={applyBatchSize}>
            <label>
              Minimum transactions per block
              <select
                value={selectedBatchSize}
                onChange={(event) => setSelectedBatchSize(event.target.value)}
              >
                {BATCH_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
            </label>
            <button className="secondary" disabled={batchUpdating || Boolean(batchError)}>
              {batchUpdating ? "Applying…" : "Apply configuration"}
            </button>
          </form>
          {batchError && <div className="banner error">Batch miner: {batchError}</div>}
          <div className="batch-metrics">
            <div><small>Pending product registrations</small><strong>{batchStatus.pendingCount}</strong></div>
            <div><small>Required transaction count</small><strong>{batchStatus.minimumTransactions}</strong></div>
            <div><small>Remaining before mining</small><strong>{batchStatus.remainingTransactions}</strong></div>
          </div>
          <h3 className="subheading">Pending product registrations</h3>
          {batchStatus.pendingRegistrations.length === 0 ? (
            <p className="muted">No valid product-registration transactions are pending.</p>
          ) : batchStatus.pendingRegistrations.map((pending) => (
            <div className="product-row compact" key={pending.hash}>
              <div>
                <strong>Commitment {formatTransaction(pending.commitment)}</strong>
                <small>Transaction {pending.hash} · nonce {pending.nonce}</small>
              </div>
              <small>Manufacturer {shorten(pending.from)}</small>
            </div>
          ))}
          {batchStatus.lastBlock && (
            <div className="result-card valid">
              <strong>Newly mined block {batchStatus.lastBlock.number}</strong>
              <p>Block hash: <code>{batchStatus.lastBlock.hash}</code></p>
              <p>Transactions included in block: {batchStatus.lastBlock.transactionCount}</p>
              <p>Product registrations confirmed: {batchStatus.lastBlock.registrationCount}</p>
              {batchStatus.lastBlock.transactionHashes.length > 0 ? (
                <ul className="hash-list">
                  {batchStatus.lastBlock.transactionHashes.map((hash) => (
                    <li key={hash}><code>{hash}</code></li>
                  ))}
                </ul>
              ) : <small>No successful product-registration transactions were included in this block.</small>}
            </div>
          )}
        </Modal>
      )}

      {activeModal === "transfer" && role === 1 && (
        <Modal title="Send a product to a distributor" onClose={() => setActiveModal("")}>
          {owned.length === 0 ? (
            <p className="muted">No products currently owned by this wallet.</p>
          ) : owned.map((item) => (
            <div className="product-row" key={item.commitment}>
              <div>
                <strong>{shorten(item.commitment)}</strong>
                <small>Registered in block {item.createdBlock} · {STATUS_NAMES[item.status]}</small>
              </div>
              {item.status === 0 && (
                <form className="transfer-form" onSubmit={(event) => transferProduct(event, item)}>
                  <input
                    value={recipient}
                    onChange={(event) => setRecipient(event.target.value)}
                    placeholder="Distributor wallet address"
                    aria-label="Distributor wallet address"
                  />
                  <button className="secondary" disabled={busy}>Start shipment</button>
                </form>
              )}
            </div>
          ))}
        </Modal>
      )}

      {activeModal === "csv" && role === 1 && contract && (
        <Modal title="Register products from CSV" onClose={() => setActiveModal("")}>
          <div className="ledger-actions">
            <a className="text-button" href="/samples/sample_products.csv" download>
              Download CSV example
            </a>
          </div>
          <p className="muted">
            Import product fields using the same commitment process as the form.
            Each row is independently signed by the local backend for this authenticated manufacturer account.
            Imports support up to {MAX_CSV_ROWS.toLocaleString("en-US")} product rows and CSV files smaller than 10 MB.
          </p>
          <form onSubmit={registerProductsCsv}>
            <label>
              Product CSV file
              <input
                ref={csvInputRef}
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
                disabled={busy}
                required
              />
            </label>
            {csvFile && <small className="muted">Selected: {csvFile.name}</small>}
            <div className="actions">
              <button className="secondary" disabled={busy || !csvFile}>
                {busy ? "Submitting CSV…" : "Validate and submit CSV"}
              </button>
              <span className="muted">Required columns: {CSV_HEADERS.join(", ")}.</span>
            </div>
          </form>
        </Modal>
      )}

      {activeModal === "ledger" && account && contract && (
        <Modal title="On-chain product records" onClose={() => setActiveModal("")}>
          <div className="ledger-actions">
            <button className="text-button" onClick={() => loadProducts()} disabled={busy}>Refresh</button>
          </div>
          {products.length === 0 ? <p className="muted">No products registered yet.</p> : (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Commitment</th><th>Manufacturer</th><th>Current owner</th><th>Status</th><th>Registration block</th><th>Bloom group</th></tr></thead>
                <tbody>{products.map((item) => (
                  <tr key={item.commitment}>
                    <td><code>{shorten(item.commitment)}</code></td>
                    <td>{shorten(item.manufacturer)}</td>
                    <td>{shorten(item.currentOwner)}</td>
                    <td>{STATUS_NAMES[item.status]}</td>
                    <td>{item.createdBlock}</td>
                    <td>Group {item.bloomGroup}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="privacy-footnote">
            Product names, manufacturer names, dosage forms, dates, and prices are not stored in this contract or in a database.
          </p>
        </Modal>
      )}
    </main>
  );
}

export default App;
