# My_Research — product supply-chain proof-of-concept

## Project layout

```text
frontend/                 React frontend and packaged ZKP/browser artifacts
backend/
  app/                    Python authentication and Anvil server
  scripts/                Startup, reset, password, and sample utilities
  data/                   Persistent Anvil state and contract metadata
  tests/                  Backend regression tests
  venv313/                Python virtual environment
  requirements.txt        Python dependencies
blockchain/
  contracts/              Solidity contracts
  circuits/               Circom source and generated ZKP artifacts
.tools/foundry/           Local Foundry/Anvil executables
scripts/                  Compatibility launchers
```

This standalone project uses a Python-hosted local EVM and a Solidity
supply-chain contract. It models two supply-chain stakeholders:

- **Manufacturer:** registers a medicine product and offers it to a distributor.
- **Distributor:** accepts the assigned shipment.
- **Contract administrator:** assigns manufacturer/distributor roles to wallet
  addresses. The deploying wallet is the administrator.

## What goes on-chain

The browser constructs a deterministic Poseidon commitment from all six product
fields. The circuit's final hash input is fixed to zero; there is no user-provided
or random salt. Registration submits that commitment and the Keccak hashes of
the product's unique, normalized character trigrams. Solidity stores the
commitment, role/custody state, registration block, and three Bloom bits in the
2048-bit exact-match Bloom group. It also inserts each product's q-gram hashes
into a separate 32768-bit Bloom filter keyed by the Ethereum block that mined
the registration. The complete q-gram hashes are emitted as public on-chain
event data for product-level Dice matching; raw product fields are not sent or
stored.

Neither the commitment nor hashed trigrams provide strong confidentiality.
Someone can guess likely product values, compute their commitment and trigrams,
and compare them with public chain data. This prototype is not suitable for
sensitive product details. The Bloom filter is a probabilistic index, not
encryption: Bloom positives can be false positives and cannot prove authenticity.

## Verification modes and comparison

The verifier enters the **complete** product details. The browser computes the
same deterministic commitment and looks it up on-chain to obtain its registration
block and Bloom group. No registration transaction hash, salt, or JSON file is
needed.

1. **Bloom-only:** tests the product's assigned group Bloom filter. A
   positive means “possible match,” not proof.
2. **Groth16-only:** generates a Circom witness and proof in the browser, then
   verifies the proof against the on-chain commitment.
3. **Fuzzy q-gram + Dice fallback:** if the exact commitment is absent, the app
   hashes normalized character trigrams from all six entered fields and screens
   the q-grams against each block's Bloom filter. It retrieves `ProductQgrams`
   events only from blocks that pass, then compares those products with the
   query using Dice similarity. The administrator, manufacturer, or distributor
   can set the shared minimum Dice threshold (initially 90%). The screening threshold is
   conservatively derived from that Dice threshold and the 256-q-gram
   per-product limit, so a product meeting the Dice threshold is not screened
   out. Bloom false positives can let extra blocks through. Results identify
   candidate products and show their scores and processing time, but fuzzy
   similarity is not proof that product details are identical.

The per-product q-gram hashes are emitted in transaction logs; the additional
block-level Bloom bits are stored in contract state and increase registration
gas usage. Existing deployments do not contain this filter and cannot be
upgraded; restart/redeploy the local chain and re-register products (for
example from the source CSV) to populate it. Restarting the local chain resets
its in-memory state.

Every product registration inserts its three Bloom bits into a group-level
2048-bit filter. Groups are assigned by successful registration order, ten
products per group: products 1–10 update group 1 even when registered in
different blockchain blocks; products 11–20 update group 2, and so on.
Registration remains one ordinary transaction per product. The contract stores
both the actual registration block and the Bloom group number.

The exact Bloom filter uses groups of 10 successful registrations; these groups
are not Ethereum block numbers. The separate q-gram Bloom filter is keyed by
actual mined block number and stores the union of q-grams from products
registered in that block. The contract screens blocks in bounded read-only
calls. The client merges adjacent passing block numbers into ranges and fetches
q-gram events only within those ranges, avoiding a scan from block zero through
the latest block. Dice scoring is limited to the products in the fetched events.
Fuzzy-search work grows with the number of blocks and the records in passing
blocks; event-query latency can be significant. The shared threshold is stored
in the contract and can be changed by any authorized stakeholder. Legacy
command-line registrations without product details remain exact-match only and
do not have q-gram records for fuzzy search.

Completed verification results focus on overall time, exact Bloom screening or proof
stages, Dice scoring, candidate counts, estimated execution gas, sampled
additional browser heap, and a theoretical complexity expression. Gas is
estimated for the on-chain `mightContain` call (exact Bloom) and the
`verifyProof` call (Groth16); no transaction gas estimate is reported for the
read-only q-gram screen or off-chain Dice work. Fuzzy results show the number
of blocks screened and passed, the number of products Dice-scored, the total
registered ledger records, and the number meeting the threshold; only
registrations with q-gram events participate in fuzzy search. Event-query
latency can dominate fuzzy wall-clock time. The
comparison table keeps the latest completed run for each verification method
until the page is refreshed. Memory is a sampled estimate when exposed by the
browser; `0.00 MB` means no additional heap was detected, not zero actual
memory. Gas is estimated for a read-only call and does not represent a mined
transaction.

The exact Bloom check is `O(3)` for its three hash probes in a fixed-size group.
For the packaged Groth16 circuit, the proving-key domain size is 2,048 and the
verifier has one public input. The UI shows the prover's FFT-dominated growth
term as `O(2048 log₂ 2048)` and the verifier term as `O(1)`; these are
theoretical growth terms for this fixed circuit, not measured operation counts.
Fuzzy computational work is `O(Q + BQ + Σqᵢ + NQ + N log N)`, excluding RPC
event retrieval latency. `Q` is the query q-gram count, `B` is the number of
Ethereum blocks with q-gram data screened, and `N` is the number of product
records in passing blocks that are Dice-scored. `Σqᵢ` is the total q-gram count across
those records. The q-gram Bloom check does at most `BQ` membership tests; the
reusable query set is built once, candidate sets are built and compared by
iterating the query set, and all scored records are sorted. The UI substitutes
the current run's values into the terms, using a rounded `N log₂N` ranking
term, explains each symbol, and displays the total below the comparison table.
These are illustrative growth-term values, not measured instruction counts
or wall-clock time; RPC event retrieval is excluded.

Fuzzy result timings separate product input/commitment preparation, exact
commitment lookup, query q-gram generation, threshold read, q-gram Bloom
screening, event retrieval, Dice scoring, ranking/filtering, result-detail
lookups, and other residual processing. The shared Dice threshold can be
changed by the administrator, manufacturer, or distributor; changes apply to
all users.

## Prerequisites

- Python 3.12+
- Internet access on first run so `py-solc-x` can download Solidity 0.8.24
- Node.js dependencies are not needed to run the packaged frontend.

The local EVM, Solidity compilation/deployment, transaction batch monitor, and
static web server run in Python. No Node.js, npm, Vite, or Hardhat process is
used to run the application. Python serves the packaged browser frontend and
proving artifacts directly; JavaScript still runs in the browser as part of
that frontend.

The Groth16 verifier and proving key are for local research only. This generated
key is **not suitable for production**. A real deployment requires a
documented, independently verifiable trusted setup, reviewed circuit,
production verifier, and security audit.

The circuit encodes product and manufacturer names as UTF-8 integers of at most
31 bytes. Price is represented in cents, dates as Unix seconds, and dosage form
as an enum. It constrains dosage form, date ordering, and input ranges.

## Run locally

Configure local application logins in PowerShell from the project directory:

```powershell
py -3.13 -m venv backend\venv313
.\backend\venv313\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
.\backend\venv313\Scripts\python.exe backend\scripts\hash_password.py
```

Run `backend\scripts\hash_password.py` three times, using a distinct password of at
least 12 characters for each of the `admin`, `manufacturer`, and `distributor`
users. Paste each output hash into that user's `passwordHash` in `.env`, keeping
the configured `accountIndex` values 0, 1, and 2. `.env` is ignored by Git and
must not be shared. The backend verifies passwords with PBKDF2-HMAC-SHA256;
the browser never receives password hashes or private keys.

The account index maps a configured login to a local-chain signer: index 0 is
the contract administrator, index 1 is initialized as Manufacturer, and index
2 is initialized as Distributor whenever contracts are freshly deployed. The
administrator can still change roles from the admin panel. On normal restarts,
existing role assignments persist from Anvil state. The Solidity role checks
and `msg.sender` attribution are unchanged.

The application uses persistent Foundry Anvil accounts and state. It derives ten
stable development accounts from the fixed Anvil development mnemonic. It never
logs or sends private keys to the browser. The login session uses an HttpOnly,
SameSite cookie and expires after eight hours. Anvil blockchain state persists
in `backend/data/anvil-state.json`, while deployment addresses persist in
`backend/data/pharmachain-deployment.json`. The local Python app binds to loopback and
is for research only, not production or real funds.

In another PowerShell terminal, run:

```powershell
.\backend\venv313\Scripts\python.exe backend\scripts\start_local_chain.py
```

The Python process compiles and deploys the contracts, starts the local EVM
JSON-RPC endpoint and batch monitor, and serves the static frontend. Keep it
running and open `http://127.0.0.1:5173`. Sign in with the configured local
application username and password. The Python backend signs each allowlisted
contract transaction with the private key for the authenticated account index;
the contract continues to authorize the corresponding stakeholder address.

Normal Python restarts reconnect to the existing Anvil chain and contract
addresses. Stopping and restarting Anvil with the saved state also preserves
state. Reset is separate and must be invoked intentionally.

To reset the development chain safely:

```powershell
.\backend\scripts\reset_anvil.ps1 -ConfirmReset YES
```

The reset script creates a timestamped backup by default, stops the app and
Anvil listeners, deletes `backend/data/anvil-state.json` and
`backend/data/pharmachain-deployment.json`, starts a fresh Anvil chain with the same
chain ID and account addresses, and requires `-ConfirmReset YES`. Use
`-SkipBackup` only if you knowingly accept losing the backup option. Use
`-StartApp` to start the Python application immediately after reset.

The manufacturer dashboard defaults to a minimum of **10 separate product
registration transactions per block**. Select 2, 5, 10, 20, or 50 and apply the
setting to experiment. Each product submission is an independent transaction
signed by the local backend; the local monitor mines as soon as the pending
count reaches the selected minimum. Registrations below the threshold remain
pending until more arrive—there is no time-based mining trigger. The dashboard
lists pending registrations and confirms the mined block, receipt-backed
transaction hashes, and block number. Other supported supply-chain actions are
mined when there are no valid pending product registrations, so they do not
flush a partial registration batch.

### Add command-line sample registrations

With the Python app running, open a second PowerShell window in the project
directory and run:

```powershell
.\backend\venv313\Scripts\python.exe backend\scripts\add_sample_data.py --count 10 --batch-size 10
```

The script prompts for the configured administrator and manufacturer
usernames and passwords, sets the chosen batch threshold, and submits each
sample through the authenticated backend signer. Before running it, sign in
to the application as admin and assign the Manufacturer role to the configured
manufacturer account. No private keys are required or exposed. Sample
commitments are opaque demo values, not hashes of product form fields, so they
appear in the ledger but cannot be used for form-based Groth16 product
verification.

### Register products from CSV in the browser

The Manufacturer dashboard also has **Register products from CSV**. Download
the example CSV from that panel or use these columns (the importer accepts
either the field names or the human-readable headings shown here):

```csv
productName,manufacturerName,dosageForm,manufacturingDate,expiryDate,price
Example Product,Example Pharma,Tablet,2025-01-15,2030-01-15,4.99
```

For example, `Product name,Manufacturer name,Dosage form,Manufacturing date,Expiry date,Price (LKR)` is also accepted.
Dates use `YYYY-MM-DD`; dosage form must be Tablet, Syrup, Capsule, Cream, or
Injection. The browser computes the same commitment and q-gram hashes as
manual form entry. It checks the on-chain commitment list once per import,
then submits each product separately through the authenticated backend signer;
the contract also rejects duplicate commitments. Accepted transactions join the
configured block batch. Raw
product fields stay in the browser; the commitment and guessable q-gram hashes
are sent on-chain. Each import supports up to 6,000 product rows and CSV files
smaller than 10 MB.

## Tests

```powershell
.\backend\venv313\Scripts\python.exe -m unittest discover -s backend/tests
```

The tests cover supported batch sizes, registration filtering, q-gram event
registration, stakeholder-controlled shared Dice threshold, and independent
transactions waiting for and confirming in one block. A 50-registration
q-gram batch was also verified to mine in a single local block. The browser's
Groth16 verification uses the packaged local WASM and proving key.

## Scope and limitations

- No application database is used.
- Product field data are transient browser inputs and are not persisted by the
  app. Re-enter the same fields to recompute the deterministic commitment.
- Commitments are unsalted and deterministic, so this version does not protect
  low-entropy product details against guessing from public chain data.
- The Bloom filter contains commitments (hashed data), never raw product fields.
- Current handoff is one product record from one manufacturer to one assigned
  distributor; quantity splitting, pharmacies, QR labels, and ZKP security
  ceremonies are outside this first milestone.
- This is a local research prototype, not a production medicines registry.
