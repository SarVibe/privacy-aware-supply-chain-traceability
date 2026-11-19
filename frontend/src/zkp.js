import { groth16 } from "snarkjs";

const WASM_URL = "/zkp/ProductCommitment.wasm";
const ZKEY_URL = "/zkp/ProductCommitment_final.zkey";

export const GROTH16_CIRCUIT_DOMAIN_SIZE = 2048;

export async function createProductProof(circuitInput) {
  const response = await groth16.fullProve(circuitInput, WASM_URL, ZKEY_URL);
  const [commitment] = response.publicSignals;
  return {
    commitment,
    proof: response.proof,
    publicSignals: response.publicSignals
  };
}

export function solidityProof(proof) {
  return {
    a: [proof.pi_a[0], proof.pi_a[1]],
    b: [
      [proof.pi_b[0][1], proof.pi_b[0][0]],
      [proof.pi_b[1][1], proof.pi_b[1][0]]
    ],
    c: [proof.pi_c[0], proof.pi_c[1]]
  };
}
