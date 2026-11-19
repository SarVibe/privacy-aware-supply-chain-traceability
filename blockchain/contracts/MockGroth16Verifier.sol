// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IGroth16Verifier.sol";

contract MockGroth16Verifier is IGroth16Verifier {
    function verifyProof(
        uint256[2] calldata,
        uint256[2][2] calldata,
        uint256[2] calldata,
        uint256[1] calldata
    ) external pure returns (bool) {
        return true;
    }
}
