
pragma circom 2.2.3;

include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";

template SupplyChainVerification() {

    // Public inputs
    signal input mode;
    signal input expectedQuantity;
    signal input referenceDate;

    // Private inputs
    signal input actualQuantity;
    signal input actualExpiry;

    // Public output: 1 = valid, 0 = invalid
    signal output isValid;

    // Mode must be either 0 or 1
    mode * (mode - 1) === 0;

    // Restrict quantity values to 64 bits
    component actualQtyBits = Num2Bits(64);
    actualQtyBits.in <== actualQuantity;

    component expectedQtyBits = Num2Bits(64);
    expectedQtyBits.in <== expectedQuantity;

    // Restrict dates to 27 bits
    component actualDateBits = Num2Bits(27);
    actualDateBits.in <== actualExpiry;

    component referenceDateBits = Num2Bits(27);
    referenceDateBits.in <== referenceDate;

    // Mode 0: Exact quantity matching
    component quantityEqual = IsEqual();
    quantityEqual.in[0] <== actualQuantity;
    quantityEqual.in[1] <== expectedQuantity;

    // Mode 1: Expiry date must be after reference date
    component expiryValid = GreaterThan(27);
    expiryValid.in[0] <== actualExpiry;
    expiryValid.in[1] <== referenceDate;

    // Select verification mode
    component isQuantityMode = IsEqual();
    isQuantityMode.in[0] <== mode;
    isQuantityMode.in[1] <== 0;

    component isExpiryMode = IsEqual();
    isExpiryMode.in[0] <== mode;
    isExpiryMode.in[1] <== 1;

    // Generate verification result
    signal quantityResult;
    signal expiryResult;

    quantityResult <== quantityEqual.out * isQuantityMode.out;
    expiryResult <== expiryValid.out * isExpiryMode.out;

    isValid <== quantityResult + expiryResult;
}

component main {public [mode, expectedQuantity, referenceDate]} = SupplyChainVerification();
