
pragma circom 2.2.3;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

// =====================================================
// Reusable String-to-Poseidon Hash Component
// Maximum string length: 62 bytes
// =====================================================

template StringHash(MAX_BYTES) {

    signal input bytes[MAX_BYTES];
    signal input length;
    signal input expectedHash;

    signal output hash;
    signal output isMatch;

    // Validate string length (0-62 bytes).
    component lengthBits = Num2Bits(6);
    lengthBits.in <== length;

    component lengthCheck = LessThan(7);
    lengthCheck.in[0] <== length;
    lengthCheck.in[1] <== MAX_BYTES + 1;
    lengthCheck.out === 1;

    component byteBits[MAX_BYTES];
    component active[MAX_BYTES];

    for (var i = 0; i < MAX_BYTES; i++) {

        // Validate each byte (0-255).
        byteBits[i] = Num2Bits(8);
        byteBits[i].in <== bytes[i];

        // Enforce zero padding.
        active[i] = LessThan(7);
        active[i].in[0] <== i;
        active[i].in[1] <== length;

        bytes[i] * (1 - active[i].out) === 0;
    }

    // Pack first 31 bytes.
    var packed0 = 0;
    var factor0 = 1;

    for (var i = 0; i < 31; i++) {
        packed0 += bytes[i] * factor0;
        factor0 *= 256;
    }

    // Pack remaining 31 bytes.
    var packed1 = 0;
    var factor1 = 1;

    for (var i = 31; i < 62; i++) {
        packed1 += bytes[i] * factor1;
        factor1 *= 256;
    }

    // Calculate Poseidon hash.
    component poseidonHash = Poseidon(3);

    poseidonHash.inputs[0] <== packed0;
    poseidonHash.inputs[1] <== packed1;
    poseidonHash.inputs[2] <== length;

    hash <== poseidonHash.out;

    // Return 1 if hashes match, otherwise 0.
    component hashEqual = IsEqual();

    hashEqual.in[0] <== poseidonHash.out;
    hashEqual.in[1] <== expectedHash;

    isMatch <== hashEqual.out;
}


// =====================================================
// Main Supply Chain Verification Component
// 7 String + 2 Date + 1 Quantity = 10 Attributes
// =====================================================

template SupplyChainVerification() {

    // -----------------------------
    // 1. String Attribute Inputs
    // -----------------------------

    // Product ID
    signal input product_id_bytes[62];
    signal input product_id_length;
    signal input product_id_expectedHash;

    // Product Name
    signal input product_name_bytes[62];
    signal input product_name_length;
    signal input product_name_expectedHash;

    // Batch Number
    signal input batch_number_bytes[62];
    signal input batch_number_length;
    signal input batch_number_expectedHash;

    // Manufacturer ID
    signal input manufacturer_id_bytes[62];
    signal input manufacturer_id_length;
    signal input manufacturer_id_expectedHash;

    // Shipment ID
    signal input shipment_id_bytes[62];
    signal input shipment_id_length;
    signal input shipment_id_expectedHash;

    // Source Location
    signal input source_location_bytes[62];
    signal input source_location_length;
    signal input source_location_expectedHash;

    // Destination Location
    signal input destination_location_bytes[62];
    signal input destination_location_length;
    signal input destination_location_expectedHash;


    // -----------------------------
    // 2. Date Attribute Inputs
    // -----------------------------

    signal input manufacturing_date;
    signal input manufacturing_date_expected;

    signal input expiry_date;
    signal input expiry_date_expected;


    // -----------------------------
    // 3. Quantity Inputs
    // -----------------------------

    signal input quantity;
    signal input quantity_expected;


    // -----------------------------
    // 4. Public Verification Output
    // -----------------------------

    signal output isValid;


    // -----------------------------
    // 5. Seven String Hash Components
    // -----------------------------

    component productIdHash = StringHash(62);
    component productNameHash = StringHash(62);
    component batchNumberHash = StringHash(62);
    component manufacturerIdHash = StringHash(62);
    component shipmentIdHash = StringHash(62);
    component sourceLocationHash = StringHash(62);
    component destinationLocationHash = StringHash(62);


    // -----------------------------
    // 6. Connect Product ID
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        productIdHash.bytes[i] <== product_id_bytes[i];
    }

    productIdHash.length <== product_id_length;
    productIdHash.expectedHash <== product_id_expectedHash;


    // -----------------------------
    // 7. Connect Product Name
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        productNameHash.bytes[i] <== product_name_bytes[i];
    }

    productNameHash.length <== product_name_length;
    productNameHash.expectedHash <== product_name_expectedHash;


    // -----------------------------
    // 8. Connect Batch Number
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        batchNumberHash.bytes[i] <== batch_number_bytes[i];
    }

    batchNumberHash.length <== batch_number_length;
    batchNumberHash.expectedHash <== batch_number_expectedHash;


    // -----------------------------
    // 9. Connect Manufacturer ID
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        manufacturerIdHash.bytes[i] <== manufacturer_id_bytes[i];
    }

    manufacturerIdHash.length <== manufacturer_id_length;
    manufacturerIdHash.expectedHash <== manufacturer_id_expectedHash;


    // -----------------------------
    // 10. Connect Shipment ID
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        shipmentIdHash.bytes[i] <== shipment_id_bytes[i];
    }

    shipmentIdHash.length <== shipment_id_length;
    shipmentIdHash.expectedHash <== shipment_id_expectedHash;


    // -----------------------------
    // 11. Connect Source Location
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        sourceLocationHash.bytes[i] <== source_location_bytes[i];
    }

    sourceLocationHash.length <== source_location_length;
    sourceLocationHash.expectedHash <== source_location_expectedHash;


    // -----------------------------
    // 12. Connect Destination Location
    // -----------------------------

    for (var i = 0; i < 62; i++) {
        destinationLocationHash.bytes[i] <== destination_location_bytes[i];
    }

    destinationLocationHash.length <== destination_location_length;
    destinationLocationHash.expectedHash <== destination_location_expectedHash;


    // -----------------------------
    // 13. Date Verification
    // -----------------------------

    // Manufacturing Date: 27-bit validation.
    component manufacturingDateBits = Num2Bits(27);
    manufacturingDateBits.in <== manufacturing_date;

    component manufacturingExpectedBits = Num2Bits(27);
    manufacturingExpectedBits.in <== manufacturing_date_expected;

    // Exact matching.
    component manufacturingDateEqual = IsEqual();

    manufacturingDateEqual.in[0] <== manufacturing_date;
    manufacturingDateEqual.in[1] <== manufacturing_date_expected;


    // Expiry Date: 27-bit validation.
    component expiryDateBits = Num2Bits(27);
    expiryDateBits.in <== expiry_date;

    component expiryExpectedBits = Num2Bits(27);
    expiryExpectedBits.in <== expiry_date_expected;

    // Exact matching.
    component expiryDateEqual = IsEqual();

    expiryDateEqual.in[0] <== expiry_date;
    expiryDateEqual.in[1] <== expiry_date_expected;


    // -----------------------------
    // 14. Quantity Verification
    // -----------------------------

    // Validate quantity as 64-bit value.
    component quantityBits = Num2Bits(64);
    quantityBits.in <== quantity;

    component quantityExpectedBits = Num2Bits(64);
    quantityExpectedBits.in <== quantity_expected;

    // Exact matching.
    component quantityEqual = IsEqual();

    quantityEqual.in[0] <== quantity;
    quantityEqual.in[1] <== quantity_expected;


    // -----------------------------
    // 15. Combine All 10 Results
    // -----------------------------

    // All attributes must match for a valid result.

    // Combine all 10 attribute matching results.
    signal match1;
    signal match2;
    signal match3;
    signal match4;
    signal match5;
    signal match6;
    signal match7;
    signal match8;
    signal match9;

    match1 <== productIdHash.isMatch * productNameHash.isMatch;
    match2 <== match1 * batchNumberHash.isMatch;
    match3 <== match2 * manufacturerIdHash.isMatch;
    match4 <== match3 * shipmentIdHash.isMatch;
    match5 <== match4 * sourceLocationHash.isMatch;
    match6 <== match5 * destinationLocationHash.isMatch;
    match7 <== match6 * manufacturingDateEqual.out;
    match8 <== match7 * expiryDateEqual.out;
    match9 <== match8 * quantityEqual.out;

    isValid <== match9;
}


// =====================================================
// Main Circuit
// Expected values are public inputs.
// Actual values remain private witness inputs.
// =====================================================

component main {
    public [
        product_id_expectedHash,
        product_name_expectedHash,
        batch_number_expectedHash,
        manufacturer_id_expectedHash,
        shipment_id_expectedHash,
        source_location_expectedHash,
        destination_location_expectedHash,
        manufacturing_date_expected,
        expiry_date_expected,
        quantity_expected
    ]
} = SupplyChainVerification();
