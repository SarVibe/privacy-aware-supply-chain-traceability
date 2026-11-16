// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title HarmonizedSupplyChain
 * @notice Component 1: Pre-Ledger Cross-Organizational Data Harmonization Smart Contract
 * @dev Implements ledger storage and retrieval for Algorithm 1:
 *      Tuple: <BloomFilter (bytes), ClusterID (string), RecordHash (bytes32), Timestamp (uint256)>
 */
contract HarmonizedSupplyChain {

    uint256 public immutable bloomFilterBytes;
    address public owner;
    bool public paused;

    struct HarmonizedRecord {
        string recordId;            // Unique shipment reference (e.g., REC_00001)
        string clusterId;           // Canonical cluster identifier (e.g., CANONICAL_CLUSTER_0001)
        bytes bloomFilter;          // 1024-bit Bloom filter (128 bytes) with or without LDP
        bytes32 recordHash;         // SHA-256 hash of raw record for tamper-evidence
        uint256 timestamp;          // Block timestamp upon commitment
        address submittedBy;        // Ethereum address of submitting stakeholder
    }

    // Candidate structure optimized for Algorithm 1 Line 4 retrieval (Zero gas view call)
    struct CandidateFilter {
        string recordId;
        string clusterId;
        bytes bloomFilter;
    }

    // Storage arrays and mappings
    HarmonizedRecord[] private records;
    mapping(string => uint256[]) private clusterToRecordIndices;
    mapping(bytes32 => bool) private existingRecordHashes;
    mapping(string => bool) private existingRecordIds;
    mapping(address => bool) public authorizedSubmitters;
    
    // Cluster leader tracking (Leader-based clustering canonical reference)
    mapping(string => bytes) private clusterLeaderFilter;
    string[] private uniqueClusterIds;
    mapping(string => bool) private clusterExists;

    // Events
    event RecordHarmonized(
        string indexed recordId,
        string indexed clusterId,
        bytes32 recordHash,
        uint256 timestamp,
        address indexed submitter
    );

    event ClusterCreated(
        string indexed clusterId,
        uint256 timestamp
    );

    event SubmitterAuthorizationUpdated(address indexed submitter, bool authorized);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event Paused(address indexed account);
    event Unpaused(address indexed account);

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the owner");
        _;
    }

    modifier onlySubmitter() {
        require(authorizedSubmitters[msg.sender], "Caller is not an authorized submitter");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract is paused");
        _;
    }

    constructor(uint256 _bloomFilterBytes) {
        require(_bloomFilterBytes > 0, "Bloom filter size must be positive");
        owner = msg.sender;
        authorizedSubmitters[msg.sender] = true;
        bloomFilterBytes = _bloomFilterBytes;
        emit OwnershipTransferred(address(0), msg.sender);
        emit SubmitterAuthorizationUpdated(msg.sender, true);
    }

    function setSubmitter(address submitter, bool authorized) external onlyOwner {
        require(submitter != address(0), "Submitter cannot be zero address");
        authorizedSubmitters[submitter] = authorized;
        emit SubmitterAuthorizationUpdated(submitter, authorized);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Owner cannot be zero address");
        address previousOwner = owner;
        owner = newOwner;
        authorizedSubmitters[newOwner] = true;
        emit OwnershipTransferred(previousOwner, newOwner);
        emit SubmitterAuthorizationUpdated(newOwner, true);
    }

    function setPaused(bool shouldPause) external onlyOwner {
        paused = shouldPause;
        if (shouldPause) {
            emit Paused(msg.sender);
        } else {
            emit Unpaused(msg.sender);
        }
    }

    /**
     * @notice Stores a harmonized supply chain record on-chain (Algorithm 1 Lines 21-22).
     * @param _recordId Unique record identifier
     * @param _clusterId Canonical cluster ID resolved by pre-ledger fuzzy matcher
     * @param _bloomFilter Keyed Bloom filter bytes (128 bytes for 1024 bits)
     * @param _recordHash Cryptographic SHA-256 hash of raw metadata
     */
    function storeHarmonizedRecord(
        string calldata _recordId,
        string calldata _clusterId,
        bytes calldata _bloomFilter,
        bytes32 _recordHash
    ) external onlySubmitter whenNotPaused returns (uint256 recordIndex) {
        require(bytes(_recordId).length > 0, "Record ID cannot be empty");
        require(bytes(_clusterId).length > 0, "Cluster ID cannot be empty");
        require(_bloomFilter.length == bloomFilterBytes, "Invalid Bloom filter length");
        require(!existingRecordIds[_recordId], "Record ID already committed");
        require(!existingRecordHashes[_recordHash], "Record hash already committed");

        recordIndex = records.length;

        // Register new canonical cluster if not seen before
        if (!clusterExists[_clusterId]) {
            clusterExists[_clusterId] = true;
            uniqueClusterIds.push(_clusterId);
            clusterLeaderFilter[_clusterId] = _bloomFilter; // First member becomes cluster leader
            emit ClusterCreated(_clusterId, block.timestamp);
        }

        // Persist record
        records.push(HarmonizedRecord({
            recordId: _recordId,
            clusterId: _clusterId,
            bloomFilter: _bloomFilter,
            recordHash: _recordHash,
            timestamp: block.timestamp,
            submittedBy: msg.sender
        }));

        clusterToRecordIndices[_clusterId].push(recordIndex);
        existingRecordIds[_recordId] = true;
        existingRecordHashes[_recordHash] = true;

        emit RecordHarmonized(_recordId, _clusterId, _recordHash, block.timestamp, msg.sender);
    }

    /**
     * @notice Algorithm 1 Line 4: C <- retrieve_stored_records(Bp)
     * @dev View function: Executes off-chain with ZERO gas cost to retrieve all candidate filters.
     */
    function getCandidateRecords() external view returns (CandidateFilter[] memory) {
        uint256 total = records.length;
        CandidateFilter[] memory candidates = new CandidateFilter[](total);

        for (uint256 i = 0; i < total; i++) {
            candidates[i] = CandidateFilter({
                recordId: records[i].recordId,
                clusterId: records[i].clusterId,
                bloomFilter: records[i].bloomFilter
            });
        }
        return candidates;
    }

    /**
     * @notice Retrieves only the canonical Leader Bloom Filters for each cluster.
     * @dev Reduces candidate comparison overhead from O(N) to O(K) where K = number of clusters.
     */
    function getClusterLeaders() external view returns (string[] memory clusterIds, bytes[] memory leaderFilters) {
        uint256 totalClusters = uniqueClusterIds.length;
        clusterIds = new string[](totalClusters);
        leaderFilters = new bytes[](totalClusters);

        for (uint256 i = 0; i < totalClusters; i++) {
            string memory cId = uniqueClusterIds[i];
            clusterIds[i] = cId;
            leaderFilters[i] = clusterLeaderFilter[cId];
        }
    }

    /**
     * @notice Total number of records stored on the ledger.
     */
    function getTotalRecords() external view returns (uint256) {
        return records.length;
    }

    /**
     * @notice Total number of unique canonical clusters on the ledger.
     */
    function getTotalClusters() external view returns (uint256) {
        return uniqueClusterIds.length;
    }

    /**
     * @notice Fetches full harmonized record details by record index.
     */
    function getRecord(uint256 _index) external view returns (
        string memory recordId,
        string memory clusterId,
        bytes memory bloomFilter,
        bytes32 recordHash,
        uint256 timestamp,
        address submittedBy
    ) {
        require(_index < records.length, "Index out of bounds");
        HarmonizedRecord storage r = records[_index];
        return (r.recordId, r.clusterId, r.bloomFilter, r.recordHash, r.timestamp, r.submittedBy);
    }

    /**
     * @notice Verification Helper (For Component 4 Integration):
     *         Checks if a given SHA-256 record hash exists in the ledger.
     */
    function verifyRecordExists(bytes32 _recordHash) external view returns (bool) {
        return existingRecordHashes[_recordHash];
    }
}