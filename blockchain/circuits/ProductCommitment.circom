pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

template ProductCommitment() {
    signal input productName;
    signal input manufacturerName;
    signal input dosageForm;
    signal input manufacturingDate;
    signal input expiryDate;
    signal input priceCents;
    signal input salt;
    signal output commitment;

    component productNameBits = Num2Bits(248);
    productNameBits.in <== productName;

    component manufacturerNameBits = Num2Bits(248);
    manufacturerNameBits.in <== manufacturerName;

    component dosageBits = Num2Bits(3);
    dosageBits.in <== dosageForm;
    component validDosage = LessThan(3);
    validDosage.in[0] <== dosageForm;
    validDosage.in[1] <== 5;
    validDosage.out === 1;

    component manufacturingDateBits = Num2Bits(32);
    manufacturingDateBits.in <== manufacturingDate;
    component expiryDateBits = Num2Bits(32);
    expiryDateBits.in <== expiryDate;

    component priceBits = Num2Bits(64);
    priceBits.in <== priceCents;
    component saltBits = Num2Bits(248);
    saltBits.in <== salt;

    component expiryAfterManufacture = LessThan(32);
    expiryAfterManufacture.in[0] <== manufacturingDate;
    expiryAfterManufacture.in[1] <== expiryDate;
    expiryAfterManufacture.out === 1;

    component hash = Poseidon(7);
    hash.inputs[0] <== productName;
    hash.inputs[1] <== manufacturerName;
    hash.inputs[2] <== dosageForm;
    hash.inputs[3] <== manufacturingDate;
    hash.inputs[4] <== expiryDate;
    hash.inputs[5] <== priceCents;
    hash.inputs[6] <== salt;
    commitment <== hash.out;
}

component main = ProductCommitment();
