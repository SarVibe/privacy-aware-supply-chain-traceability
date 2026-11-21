// SPDX-License-Identifier: MIT
pragma solidity ^0.8.34;

import "./Groth16Verifier.sol";

contract ZKPVerifier {

    // Define the six stakeholder roles
    enum Role {
        None,
        Admin,
        Manufacturer,
        LogisticsProvider,
        Warehouse,
        Distributor,
        Pharmacy
    }

    // Groth16 verifier contract
    Groth16Verifier public groth16Verifier;

    // Contract owner (Admin)
    address public owner;

    // Store stakeholder roles
    mapping(address => Role) public stakeholderRoles;

    // Events
    event StakeholderRegistered(address indexed stakeholder, Role role);
    event StakeholderRevoked(address indexed stakeholder);
    event VerificationCompleted(
        address indexed stakeholder,
        Role role,
        uint256 timestamp
    );
    // Initialize the verifier contract
    constructor(address _groth16Verifier) {
        require(_groth16Verifier != address(0), "Invalid verifier address");

        owner = msg.sender;
        groth16Verifier = Groth16Verifier(_groth16Verifier);

        // Contract deployer becomes Admin
        stakeholderRoles[msg.sender] = Role.Admin;
    }

    // Restrict functions to Admin
    modifier onlyAdmin() {
        require(msg.sender == owner, "Only Admin can perform this action");
        _;
    }

    // Register a stakeholder and assign a role
    function registerStakeholder(
        address stakeholder,
        Role role
    ) external onlyAdmin {

        require(stakeholder != address(0), "Invalid stakeholder address");
        require(role != Role.None, "Invalid stakeholder role");
        require(role != Role.Admin, "Cannot assign Admin role");
        require(
            stakeholderRoles[stakeholder] == Role.None,
            "Stakeholder already registered"
        );

        stakeholderRoles[stakeholder] = role;

        emit StakeholderRegistered(stakeholder, role);
    }

    // Revoke a stakeholder's access
    function revokeStakeholder(
        address stakeholder
    ) external onlyAdmin {

        require(
            stakeholderRoles[stakeholder] != Role.None,
            "Stakeholder not registered"
        );

        stakeholderRoles[stakeholder] = Role.None;

        emit StakeholderRevoked(stakeholder);
    }

    // Check whether a stakeholder can access requested attributes
    function canAccessAttribute(
        Role role,
        uint256 attributeIndex
    ) public pure returns (bool) {

        if (attributeIndex >= 10) {
            return false;
        }

        // Manufacturer: All 10 attributes
        if (role == Role.Manufacturer) {
            return true;
        }

        // Logistics Provider: 0, 2, 4, 6, 7, 8, 9
        if (role == Role.LogisticsProvider) {
            return (
                attributeIndex == 0 ||
                attributeIndex == 2 ||
                attributeIndex == 4 ||
                attributeIndex == 6 ||
                attributeIndex == 7 ||
                attributeIndex == 8 ||
                attributeIndex == 9
            );
        }

        // Warehouse: All 10 attributes
        if (role == Role.Warehouse) {
            return true;
        }

        // Distributor: All except quantity (7)
        if (role == Role.Distributor) {
            return attributeIndex != 7;
        }

        // Pharmacy: product_id, product_name, batch_number,
        // manufacturing_date and expiry_date
        if (role == Role.Pharmacy) {
            return attributeIndex <= 4;
        }

        // Admin and None have no attribute access
        return false;
    }

    // Verify a supply-chain record using a Groth16 proof
    function verifySupplyChain(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[11] calldata _pubSignals,
        uint256[] calldata requestedAttributes
    ) external returns (bool) {

        Role role = stakeholderRoles[msg.sender];

        // Only registered operational stakeholders
        require(role != Role.None, "Stakeholder not registered");
        require(role != Role.Admin, "Admin cannot verify records");

        // At least one attribute must be requested
        require(
            requestedAttributes.length > 0,
            "No attributes requested"
        );

        // Check role-based attribute permissions
        for (uint256 i = 0; i < requestedAttributes.length; i++) {

            require(
                canAccessAttribute(role, requestedAttributes[i]),
                "Attribute access denied"
            );

            // Prevent duplicate attribute requests
            for (uint256 j = 0; j < i; j++) {
                require(
                    requestedAttributes[i] != requestedAttributes[j],
                    "Duplicate attribute"
                );
            }
        }

        // Check the public validity output
        require(_pubSignals[0] == 1, "Supply-chain data mismatch");

        // Verify the Groth16 proof
        require(
            groth16Verifier.verifyProof(_pA, _pB, _pC, _pubSignals),
            "Invalid zero-knowledge proof"
        );

    emit VerificationCompleted(msg.sender, role, block.timestamp);

    return true;
    }    
}