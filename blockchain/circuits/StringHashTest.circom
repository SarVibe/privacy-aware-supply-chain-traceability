pragma circom 2.2.3;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

template StringHash(MAX_BYTES) {

    signal input bytes[MAX_BYTES];
    signal input length;
    signal input expectedHash;

    signal output hash;

    // Validate string length (maximum 62 bytes).
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

    // Exact hash matching constraint.
    poseidonHash.out === expectedHash;
}

component main {public [length, expectedHash]} = StringHash(62);