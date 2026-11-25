pragma circom 2.2.3;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

// Convert a string of up to 62 bytes into one field element.
template StringEncode(MAX_BYTES) {
    signal input bytes[MAX_BYTES];
    signal input length;

    signal output hash;

    component lengthBits = Num2Bits(6);
    lengthBits.in <== length;

    component lengthCheck = LessThan(7);
    lengthCheck.in[0] <== length;
    lengthCheck.in[1] <== MAX_BYTES + 1;
    lengthCheck.out === 1;

    component byteBits[MAX_BYTES];
    component active[MAX_BYTES];

    for (var i = 0; i < MAX_BYTES; i++) {
        byteBits[i] = Num2Bits(8);
        byteBits[i].in <== bytes[i];

        active[i] = LessThan(7);
        active[i].in[0] <== i;
        active[i].in[1] <== length;

        bytes[i] * (1 - active[i].out) === 0;
    }

    var packed0 = 0;
    var factor0 = 1;

    for (var i = 0; i < 31; i++) {
        packed0 += bytes[i] * factor0;
        factor0 *= 256;
    }

    var packed1 = 0;
    var factor1 = 1;

    for (var i = 31; i < 62; i++) {
        packed1 += bytes[i] * factor1;
        factor1 *= 256;
    }

    component poseidonHash = Poseidon(3);
    poseidonHash.inputs[0] <== packed0;
    poseidonHash.inputs[1] <== packed1;
    poseidonHash.inputs[2] <== length;

    hash <== poseidonHash.out;
}

// Calculate a salted commitment and enforce matching when enabled.
template SaltedCommitment() {
    signal input value;
    signal input salt;
    signal input expectedCommitment;
    signal input enabled;

    // Ensure enabled is either 0 or 1.
    enabled * (enabled - 1) === 0;

    // Restrict the salt to 248 bits.
    component saltBits = Num2Bits(248);
    saltBits.in <== salt;

    component commitmentHash = Poseidon(2);

    commitmentHash.inputs[0] <== value;
    commitmentHash.inputs[1] <== salt;

    // Enforce matching for role-permitted attributes.
    enabled * (commitmentHash.out - expectedCommitment) === 0;
}

// Determine mandatory attributes from the stakeholder role.
template RolePolicy() {
    signal input role;
    signal output enabled[10];
    signal output validRole;

    component manufacturer = IsEqual();
    component logistics = IsEqual();
    component warehouse = IsEqual();
    component distributor = IsEqual();
    component pharmacy = IsEqual();

    manufacturer.in[0] <== role;
    manufacturer.in[1] <== 2;

    logistics.in[0] <== role;
    logistics.in[1] <== 3;

    warehouse.in[0] <== role;
    warehouse.in[1] <== 4;

    distributor.in[0] <== role;
    distributor.in[1] <== 5;

    pharmacy.in[0] <== role;
    pharmacy.in[1] <== 6;

    validRole <== manufacturer.out
               + logistics.out
               + warehouse.out
               + distributor.out
               + pharmacy.out;

    validRole === 1;

    // Attribute indexes: 0 to 9.
    enabled[0] <== validRole;
    enabled[1] <== manufacturer.out + warehouse.out
                 + distributor.out + pharmacy.out;
    enabled[2] <== validRole;
    enabled[3] <== manufacturer.out + warehouse.out
                 + distributor.out + pharmacy.out;
    enabled[4] <== validRole;
    enabled[5] <== manufacturer.out + warehouse.out
                 + distributor.out;
    enabled[6] <== manufacturer.out + logistics.out
                + warehouse.out + distributor.out;
    enabled[7] <== manufacturer.out + logistics.out
                 + warehouse.out;
    enabled[8] <== manufacturer.out + logistics.out
                + warehouse.out + distributor.out;
    enabled[9] <== manufacturer.out + logistics.out
                + warehouse.out + distributor.out;
}

// Main role-based selective supply-chain verification circuit.
template SelectiveSupplyChain() {

    // Public inputs.
    signal input commitments[10];
    signal input role;

    // Private string attribute inputs.
    signal input stringBytes[7][62];
    signal input stringLengths[7];

    // Private numeric attribute inputs.
    signal input manufacturing_date;
    signal input expiry_date;
    signal input quantity;

    // Private random salts.
    signal input salts[10];

    // Determine mandatory attributes.
    component policy = RolePolicy();
    policy.role <== role;

    // Encode seven string attributes using their correct indexes.
    component stringEncoders[7];

    signal attributeValues[10];

    for (var i = 0; i < 7; i++) {
        stringEncoders[i] = StringEncode(62);

        for (var j = 0; j < 62; j++) {
            stringEncoders[i].bytes[j] <== stringBytes[i][j];
        }

        stringEncoders[i].length <== stringLengths[i];
    }

    // Required string attributes must not be empty.
    component emptyChecks[7];

    var stringAttributeIndexes[7] = [0, 1, 2, 5, 6, 8, 9];

    for (var i = 0; i < 7; i++) {
        emptyChecks[i] = IsEqual();

        emptyChecks[i].in[0] <== stringLengths[i];
        emptyChecks[i].in[1] <== 0;

        policy.enabled[stringAttributeIndexes[i]]
            * emptyChecks[i].out === 0;
    }

    // String attribute indexes: 0, 1, 2, 5, 6, 8, 9.
    attributeValues[0] <== stringEncoders[0].hash;
    attributeValues[1] <== stringEncoders[1].hash;
    attributeValues[2] <== stringEncoders[2].hash;
    attributeValues[5] <== stringEncoders[3].hash;
    attributeValues[6] <== stringEncoders[4].hash;
    attributeValues[8] <== stringEncoders[5].hash;
    attributeValues[9] <== stringEncoders[6].hash;

    // Numeric attribute indexes: 3, 4, 7.
    attributeValues[3] <== manufacturing_date;
    attributeValues[4] <== expiry_date;
    attributeValues[7] <== quantity;

    // Validate dates.
    component manufacturingBits = Num2Bits(27);
    manufacturingBits.in <== manufacturing_date;

    component expiryBits = Num2Bits(27);
    expiryBits.in <== expiry_date;

    // Validate quantity.
    component quantityBits = Num2Bits(64);
    quantityBits.in <== quantity;

    // Verify all role-permitted commitments.
    component checks[10];

    for (var i = 0; i < 10; i++) {
        checks[i] = SaltedCommitment();

        checks[i].value <== attributeValues[i];
        checks[i].salt <== salts[i];
        checks[i].expectedCommitment <== commitments[i];
        checks[i].enabled <== policy.enabled[i];
    }
}

component main {public [commitments, role]} = SelectiveSupplyChain();

