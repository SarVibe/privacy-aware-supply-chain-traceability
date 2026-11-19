// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IGroth16Verifier.sol";

contract PharmaSupplyChain {
    enum StakeholderRole {
        None,
        Manufacturer,
        Distributor
    }

    enum ProductStatus {
        Registered,
        InTransit,
        Delivered
    }

    struct ProductRecord {
        address manufacturer;
        address currentOwner;
        address pendingDistributor;
        uint64 createdBlock;
        uint64 bloomGroup;
        ProductStatus status;
        bool exists;
    }

    uint256 private constant BLOOM_WORDS = 8;
    uint256 private constant BLOOM_BITS = BLOOM_WORDS * 256;
    // Q-gram hashes are already Keccak outputs; one bit keeps writes bounded.
    uint256 private constant QGRAM_BLOOM_WORDS = 128;
    uint256 private constant QGRAM_BLOOM_BITS = QGRAM_BLOOM_WORDS * 256;
    uint256 private constant MAX_QGRAMS = 256;
    uint256 private constant MAX_QGRAM_BLOCKS_PER_SCREEN_CALL = 16;
    uint256 public constant BLOOM_GROUP_SIZE = 10;

    address public immutable administrator;
    IGroth16Verifier public immutable verifier;
    uint8 public fuzzyThresholdPercent = 90;

    mapping(address => StakeholderRole) public stakeholderRoles;
    mapping(bytes32 => ProductRecord) private products;
    mapping(uint256 => uint256[BLOOM_WORDS]) private groupBloomFilters;
    mapping(uint256 => uint256[QGRAM_BLOOM_WORDS]) private blockQgramBloomFilters;
    mapping(uint256 => bool) private hasQgramBloomBlock;
    uint256[] private qgramBloomBlockNumbers;
    bytes32[] private productCommitments;

    event StakeholderRoleUpdated(address indexed stakeholder, StakeholderRole role);
    event ProductRegistered(
        bytes32 indexed commitment,
        address indexed manufacturer,
        uint256 indexed blockNumber,
        uint256 bloomGroup
    );
    event ProductQgrams(
        bytes32 indexed commitment,
        uint256 indexed bloomGroup,
        uint256 indexed blockNumber,
        bytes32[] qgramHashes
    );
    event ShipmentInitiated(
        bytes32 indexed commitment,
        address indexed manufacturer,
        address indexed distributor
    );
    event ShipmentAccepted(
        bytes32 indexed commitment,
        address indexed distributor,
        uint256 timestamp
    );

    modifier onlyAdministrator() {
        require(msg.sender == administrator, "Only administrator");
        _;
    }

    modifier onlyManufacturer() {
        require(
            stakeholderRoles[msg.sender] == StakeholderRole.Manufacturer,
            "Manufacturer role required"
        );
        _;
    }

    modifier onlyDistributor() {
        require(
            stakeholderRoles[msg.sender] == StakeholderRole.Distributor,
            "Distributor role required"
        );
        _;
    }

    constructor(address verifierAddress) {
        require(verifierAddress != address(0), "Verifier cannot be zero");
        administrator = msg.sender;
        verifier = IGroth16Verifier(verifierAddress);
    }

    function setStakeholderRole(
        address stakeholder,
        StakeholderRole role
    ) external onlyAdministrator {
        require(stakeholder != address(0), "Stakeholder cannot be zero");
        stakeholderRoles[stakeholder] = role;
        emit StakeholderRoleUpdated(stakeholder, role);
    }

    function registerProduct(bytes32 commitment) external onlyManufacturer {
        _registerProduct(commitment, new bytes32[](0));
    }

    function registerProduct(
        bytes32 commitment,
        bytes32[] calldata qgramHashes
    ) external onlyManufacturer {
        require(qgramHashes.length <= MAX_QGRAMS, "Too many q-grams");
        _registerProduct(commitment, qgramHashes);
    }

    function _registerProduct(
        bytes32 commitment,
        bytes32[] memory qgramHashes
    ) private {
        require(commitment != bytes32(0), "Commitment cannot be zero");
        require(!products[commitment].exists, "Product already registered");

        uint64 registrationBlock = uint64(block.number);
        uint64 bloomGroup = uint64(productCommitments.length / BLOOM_GROUP_SIZE + 1);
        products[commitment] = ProductRecord({
            manufacturer: msg.sender,
            currentOwner: msg.sender,
            pendingDistributor: address(0),
            createdBlock: registrationBlock,
            bloomGroup: bloomGroup,
            status: ProductStatus.Registered,
            exists: true
        });
        productCommitments.push(commitment);
        _addToGroupBloom(bloomGroup, commitment);

        emit ProductRegistered(commitment, msg.sender, block.number, bloomGroup);
        if (qgramHashes.length > 0) {
            if (!hasQgramBloomBlock[block.number]) {
                hasQgramBloomBlock[block.number] = true;
                qgramBloomBlockNumbers.push(block.number);
            }
            _addToBlockQgramBloom(block.number, qgramHashes);
            emit ProductQgrams(
                commitment,
                bloomGroup,
                block.number,
                qgramHashes
            );
        }
    }

    function setFuzzyThresholdPercent(uint8 threshold) external {
        require(
            msg.sender == administrator ||
                stakeholderRoles[msg.sender] != StakeholderRole.None,
            "Authorized stakeholder required"
        );
        require(threshold > 0 && threshold <= 100, "Threshold must be 1-100");
        fuzzyThresholdPercent = threshold;
    }

    function getQgramCandidateBlocks(
        bytes32[] calldata queryQgramHashes,
        uint256 minimumMatches,
        uint256 firstBlockIndex,
        uint256 blockLimit
    ) external view returns (
        uint256[] memory candidateBlocks,
        uint256 totalBlocks
    ) {
        require(
            queryQgramHashes.length > 0 &&
                queryQgramHashes.length <= MAX_QGRAMS,
            "Invalid query q-gram count"
        );
        require(minimumMatches > 0, "Minimum matches must be positive");
        require(
            blockLimit > 0 &&
                blockLimit <= MAX_QGRAM_BLOCKS_PER_SCREEN_CALL,
            "Invalid block screen range"
        );

        totalBlocks = qgramBloomBlockNumbers.length;
        if (
            minimumMatches > queryQgramHashes.length ||
            firstBlockIndex >= totalBlocks
        ) {
            return (new uint256[](0), totalBlocks);
        }

        uint256 endBlockIndex = firstBlockIndex + blockLimit;
        if (endBlockIndex > totalBlocks) endBlockIndex = totalBlocks;
        candidateBlocks = new uint256[](endBlockIndex - firstBlockIndex);
        uint256 candidateCount;
        for (
            uint256 index = firstBlockIndex;
            index < endBlockIndex;
            index++
        ) {
            uint256 blockNumber = qgramBloomBlockNumbers[index];
            uint256 matches;
            for (
                uint256 queryIndex;
                queryIndex < queryQgramHashes.length;
                queryIndex++
            ) {
                uint256 bitIndex =
                    uint256(queryQgramHashes[queryIndex]) %
                    QGRAM_BLOOM_BITS;
                if (
                    (blockQgramBloomFilters[blockNumber][bitIndex / 256] &
                        (uint256(1) << (bitIndex % 256))) != 0
                ) {
                    matches++;
                    if (matches >= minimumMatches) break;
                }
            }
            if (matches >= minimumMatches) {
                candidateBlocks[candidateCount] = blockNumber;
                candidateCount++;
            }
        }

        assembly ("memory-safe") {
            mstore(candidateBlocks, candidateCount)
        }
    }

    function transferToDistributor(
        bytes32 commitment,
        address distributor
    ) external onlyManufacturer {
        ProductRecord storage product = products[commitment];
        require(product.exists, "Product does not exist");
        require(product.manufacturer == msg.sender, "Not original manufacturer");
        require(product.status == ProductStatus.Registered, "Product not transferable");
        require(
            stakeholderRoles[distributor] == StakeholderRole.Distributor,
            "Recipient must be a distributor"
        );
        require(distributor != msg.sender, "Cannot transfer to yourself");

        product.pendingDistributor = distributor;
        product.status = ProductStatus.InTransit;
        emit ShipmentInitiated(commitment, msg.sender, distributor);
    }

    function acceptShipment(bytes32 commitment) external onlyDistributor {
        ProductRecord storage product = products[commitment];
        require(product.exists, "Product does not exist");
        require(product.status == ProductStatus.InTransit, "Product not in transit");
        require(product.pendingDistributor == msg.sender, "Not the assigned distributor");

        product.currentOwner = msg.sender;
        product.pendingDistributor = address(0);
        product.status = ProductStatus.Delivered;
        emit ShipmentAccepted(commitment, msg.sender, block.timestamp);
    }

    function getProduct(
        bytes32 commitment
    )
        external
        view
        returns (
            address manufacturer,
            address currentOwner,
            address pendingDistributor,
            uint64 createdBlock,
            uint64 bloomGroup,
            ProductStatus status,
            bool exists
        )
    {
        ProductRecord storage product = products[commitment];
        return (
            product.manufacturer,
            product.currentOwner,
            product.pendingDistributor,
            product.createdBlock,
            product.bloomGroup,
            product.status,
            product.exists
        );
    }

    function getProductCommitments() external view returns (bytes32[] memory) {
        return productCommitments;
    }

    function mightContain(
        uint256 bloomGroup,
        bytes32 commitment
    ) public view returns (bool) {
        uint256 first = uint256(keccak256(abi.encode(commitment))) % BLOOM_BITS;
        uint256 second =
            uint256(keccak256(abi.encodePacked(commitment, uint8(1)))) %
            BLOOM_BITS;
        uint256 third =
            uint256(keccak256(abi.encodePacked(commitment, uint8(2)))) %
            BLOOM_BITS;
        return
            _bitIsSet(bloomGroup, first) &&
            _bitIsSet(bloomGroup, second) &&
            _bitIsSet(bloomGroup, third);
    }

    function verifyProof(
        bytes32 commitment,
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[1] calldata publicSignals
    ) external view returns (bool) {
        if (!products[commitment].exists) return false;
        if (publicSignals[0] != uint256(commitment)) return false;
        return verifier.verifyProof(a, b, c, publicSignals);
    }

    function verifyHybrid(
        bytes32 commitment,
        uint256 bloomGroup,
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[1] calldata publicSignals
    ) external view returns (bool) {
        ProductRecord storage product = products[commitment];
        if (!product.exists || product.bloomGroup != bloomGroup) return false;
        if (!mightContain(bloomGroup, commitment)) return false;
        if (publicSignals[0] != uint256(commitment)) return false;
        return verifier.verifyProof(a, b, c, publicSignals);
    }

    function _addToGroupBloom(uint256 bloomGroup, bytes32 commitment) private {
        uint256 first = uint256(keccak256(abi.encode(commitment))) % BLOOM_BITS;
        uint256 second =
            uint256(keccak256(abi.encodePacked(commitment, uint8(1)))) %
            BLOOM_BITS;
        uint256 third =
            uint256(keccak256(abi.encodePacked(commitment, uint8(2)))) %
            BLOOM_BITS;
        _setBit(bloomGroup, first);
        _setBit(bloomGroup, second);
        _setBit(bloomGroup, third);
    }

    function _addToBlockQgramBloom(
        uint256 blockNumber,
        bytes32[] memory qgramHashes
    ) private {
        for (uint256 index; index < qgramHashes.length; index++) {
            uint256 bitIndex =
                uint256(qgramHashes[index]) %
                QGRAM_BLOOM_BITS;
            blockQgramBloomFilters[blockNumber][bitIndex / 256] |=
                uint256(1) <<
                (bitIndex % 256);
        }
    }

    function _setBit(uint256 bloomGroup, uint256 bitIndex) private {
        groupBloomFilters[bloomGroup][bitIndex / 256] |=
            uint256(1) <<
            (bitIndex % 256);
    }

    function _bitIsSet(
        uint256 bloomGroup,
        uint256 bitIndex
    ) private view returns (bool) {
        return
            (groupBloomFilters[bloomGroup][bitIndex / 256] &
                (uint256(1) << (bitIndex % 256))) != 0;
    }
}
