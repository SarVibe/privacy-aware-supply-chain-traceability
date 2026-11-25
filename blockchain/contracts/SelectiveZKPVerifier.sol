// SPDX-License-Identifier: MIT
pragma solidity ^0.8.34;

import "./SelectiveGroth16Verifier.sol";

contract SelectiveZKPVerifier {

    enum Role {
        None,
        Admin,
        Manufacturer,
        LogisticsProvider,
        Warehouse,
        Distributor,
        Pharmacy
    }

    struct Record {
        address manufacturer;
        uint256 createdAt;
        uint256[10] commitments;
        bool exists;
    }

    SelectiveGroth16Verifier public groth16Verifier;
    address public owner;

    uint256 public nextRecordId = 1;

    mapping(address => Role) public stakeholderRoles;
    mapping(uint256 => Record) private records;

    event StakeholderRegistered(address indexed stakeholder, Role role);
    event StakeholderRevoked(address indexed stakeholder);

    event RecordStored(
        uint256 indexed recordId,
        address indexed manufacturer,
        uint256 timestamp
    );

    event VerificationCompleted(
        uint256 indexed recordId,
        address indexed stakeholder,
        Role role,
        uint256 attributeMask,
        uint256 timestamp
    );

    constructor(address _groth16Verifier) {
        require(_groth16Verifier != address(0), "Invalid verifier address");

        owner = msg.sender;
        groth16Verifier = SelectiveGroth16Verifier(_groth16Verifier);
        stakeholderRoles[msg.sender] = Role.Admin;
    }

    modifier onlyAdmin() {
        require(msg.sender == owner, "Only Admin can perform this action");
        _;
    }

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

    function revokeStakeholder(address stakeholder) external onlyAdmin {
        require(
            stakeholderRoles[stakeholder] != Role.None,
            "Stakeholder not registered"
        );
        require(
            stakeholderRoles[stakeholder] != Role.Admin,
            "Cannot revoke Admin"
        );

        stakeholderRoles[stakeholder] = Role.None;

        emit StakeholderRevoked(stakeholder);
    }

    function canAccessAttribute(
        Role role,
        uint256 attributeIndex
    ) public pure returns (bool) {
        if (attributeIndex >= 10) return false;

        if (role == Role.Manufacturer || role == Role.Warehouse) {
            return true;
        }

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

        if (role == Role.Distributor) {
            return attributeIndex != 7;
        }

        if (role == Role.Pharmacy) {
            return attributeIndex <= 4;
        }

        return false;
    }

    function storeRecord(
        uint256[10] calldata commitments
    ) external returns (uint256) {
        require(
            stakeholderRoles[msg.sender] == Role.Manufacturer,
            "Only Manufacturer can store records"
        );

        uint256 recordId = nextRecordId++;

        Record storage record = records[recordId];

        record.manufacturer = msg.sender;
        record.createdAt = block.timestamp;
        record.exists = true;

        for (uint256 i = 0; i < 10; i++) {
            record.commitments[i] = commitments[i];
        }

        emit RecordStored(recordId, msg.sender, block.timestamp);

        return recordId;
    }

    function verifySupplyChain(
        uint256 recordId,
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC
    ) external returns (bool) {
        Role role = stakeholderRoles[msg.sender];

        require(role != Role.None, "Stakeholder not registered");
        require(role != Role.Admin, "Admin cannot verify records");

        Record storage record = records[recordId];

        require(record.exists, "Record does not exist");

        uint[11] memory publicSignals;

        for (uint256 i = 0; i < 10; i++) {
            publicSignals[i] = record.commitments[i];
        }

        publicSignals[10] = uint256(role);

        require(
            groth16Verifier.verifyProof(
                _pA,
                _pB,
                _pC,
                publicSignals
            ),
            "Invalid zero-knowledge proof"
        );

        uint256 attributeMask = 0;

        for (uint256 i = 0; i < 10; i++) {
            if (canAccessAttribute(role, i)) {
                attributeMask |= (uint256(1) << i);
            }
        }

        emit VerificationCompleted(
            recordId,
            msg.sender,
            role,
            attributeMask,
            block.timestamp
        );

        return true;
    }

    function getRecordCommitments(
        uint256 recordId
    ) external view returns (uint256[10] memory) {
        require(records[recordId].exists, "Record does not exist");

        return records[recordId].commitments;
    }

    function getRecordInfo(
        uint256 recordId
    ) external view returns (
        address manufacturer,
        uint256 createdAt,
        bool exists
    ) {
        Record storage record = records[recordId];

        return (
            record.manufacturer,
            record.createdAt,
            record.exists
        );
    }
}
