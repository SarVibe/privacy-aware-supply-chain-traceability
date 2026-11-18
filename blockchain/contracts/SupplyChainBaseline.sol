
// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/**
 * SupplyChainBaseline
 *
 * Research baseline: Full-Rebuild Bloom Filter.
 *
 * Python computes all Bloom filters.
 * Solidity stores the authoritative product ledger and
 * complete published index generations.
 *
 * Every successful mutation increments stateRevision.
 * An index is current only when:
 *
 * publishedIndexRevision == stateRevision
 */
contract SupplyChainBaseline {

    // ============================================================
    // 1. ACCESS CONTROL
    // ============================================================

    bytes32 public constant ADMIN = keccak256("ADMIN");
    bytes32 public constant WRITER = keccak256("WRITER");
    bytes32 public constant INDEX_PUBLISHER =
        keccak256("INDEX_PUBLISHER");

    mapping(bytes32 => mapping(address => bool)) private roles;

    address public immutable initialAdmin;

    modifier onlyRole(bytes32 role) {
        require(roles[role][msg.sender], "Unauthorized role");
        _;
    }

    constructor() {
        initialAdmin = msg.sender;
        roles[ADMIN][msg.sender] = true;
    }

    event RoleGranted(
        bytes32 indexed role,
        address indexed account,
        address indexed grantedBy
    );

    event RoleRevoked(
        bytes32 indexed role,
        address indexed account,
        address indexed revokedBy
    );

    function hasRole(
        bytes32 role,
        address account
    ) external view returns (bool) {
        return roles[role][account];
    }

    function grantRole(
        bytes32 role,
        address account
    ) external onlyRole(ADMIN) {
        require(account != address(0), "Zero address");

        require(
            role == ADMIN ||
            role == WRITER ||
            role == INDEX_PUBLISHER,
            "Unknown role"
        );

        require(!roles[role][account], "Already granted");

        roles[role][account] = true;

        emit RoleGranted(role, account, msg.sender);
    }

    function revokeRole(
        bytes32 role,
        address account
    ) external onlyRole(ADMIN) {
        require(
            role == ADMIN ||
            role == WRITER ||
            role == INDEX_PUBLISHER,
            "Unknown role"
        );

        require(roles[role][account], "Role not assigned");

        if (role == ADMIN) {
            require(account != initialAdmin, "Cannot revoke initial admin");
        }

        roles[role][account] = false;

        emit RoleRevoked(role, account, msg.sender);
    }


    // ============================================================
    // 2. PRODUCT LEDGER
    // ============================================================

    enum Operation {
        INSERT,
        UPDATE,
        DELETE
    }

    struct ProductVersion {
        uint256 versionId;
        string productId;
        uint256 versionNumber;
        uint256 previousVersionId;
        Operation operation;
        string canonicalPayload;
        bytes32 payloadDigest;
        address writer;
        uint256 timestamp;
        uint256 sourceBlockNumber;
    }

    uint256 public nextVersionId = 1;

    mapping(bytes32 => uint256[]) private productHistory;

    mapping(uint256 => ProductVersion) private versions;

    mapping(bytes32 => uint256) private latestVersion;

    mapping(bytes32 => bool) private activeProducts;

    string[] private productIds;

    mapping(bytes32 => bool) private productEverRegistered;

    mapping(bytes32 => bool) public usedOperationIds;

    uint256 public stateRevision;

    uint256 public activeProductCount;

    event ProductMutation(
        bytes32 indexed operationId,
        string productId,
        uint256 indexed versionId,
        Operation operation,
        bytes32 payloadDigest,
        address indexed writer,
        uint256 sourceBlockNumber,
        uint256 stateRevision
    );

    modifier validProductId(string calldata productId) {
        require(bytes(productId).length > 0, "Empty product ID");
        require(bytes(productId).length <= 128, "Product ID too long");
        _;
    }

    function productKey(
        string memory productId
    ) public pure returns (bytes32) {
        return keccak256(bytes(productId));
    }

    function activeProductsBefore(
        uint256 versionId
    ) internal view returns (bool) {
        return versions[versionId].operation != Operation.DELETE;
    }

   function _commit(
        bytes32 operationId,
        string calldata productId,
        Operation operation,
        string memory canonicalPayload,
        bytes32 suppliedDigest
    ) internal returns (uint256 newVersionId) {

        require(operationId != bytes32(0), "Empty operation ID");

        require(
            !usedOperationIds[operationId],
            "Operation already used"
        );

        require(
            keccak256(bytes(canonicalPayload)) == suppliedDigest,
            "Payload digest mismatch"
        );

        bytes32 key = productKey(productId);

        uint256 previousId = latestVersion[key];

        uint256 versionNumber = 1;

        if (previousId != 0) {
            versionNumber =
                versions[previousId].versionNumber + 1;
        }

        newVersionId = nextVersionId++;

        versions[newVersionId] = ProductVersion({
            versionId: newVersionId,
            productId: productId,
            versionNumber: versionNumber,
            previousVersionId: previousId,
            operation: operation,
            canonicalPayload: canonicalPayload,
            payloadDigest: suppliedDigest,
            writer: msg.sender,
            timestamp: block.timestamp,
            sourceBlockNumber: block.number
        });

        productHistory[key].push(newVersionId);

        latestVersion[key] = newVersionId;

        usedOperationIds[operationId] = true;

        if (!productEverRegistered[key]) {
            productEverRegistered[key] = true;
            productIds.push(productId);
        }

        if (operation == Operation.DELETE) {
            require(activeProductCount > 0, "Invalid active count");

            activeProducts[key] = false;
            activeProductCount--;
        } else {
            activeProducts[key] = true;

            if (
                previousId == 0 ||
                !activeProductsBefore(previousId)
            ) {
                activeProductCount++;
            }
        }

        stateRevision++;

        emit ProductMutation(
            operationId,
            productId,
            newVersionId,
            operation,
            suppliedDigest,
            msg.sender,
            block.number,
            stateRevision
        );
    }


    // ============================================================
    // 3. PRODUCT INSERT / UPDATE / DELETE
    // ============================================================

    function insertProduct(
        bytes32 operationId,
        string calldata productId,
        string calldata canonicalPayload,
        bytes32 suppliedDigest,
        uint256 expectedVersionId
    )
        external
        onlyRole(WRITER)
        validProductId(productId)
        returns (uint256)
    {
        bytes32 key = productKey(productId);

        uint256 currentId = latestVersion[key];

        require(
            currentId == expectedVersionId,
            "Expected version conflict"
        );

        require(
            currentId == 0 || !activeProducts[key],
            "Product already active"
        );

        return _commit(
            operationId,
            productId,
            Operation.INSERT,
            canonicalPayload,
            suppliedDigest
        );
    }

    function updateProduct(
        bytes32 operationId,
        string calldata productId,
        uint256 expectedVersionId,
        string calldata canonicalPayload,
        bytes32 suppliedDigest
    )
        external
        onlyRole(WRITER)
        validProductId(productId)
        returns (uint256)
    {
        bytes32 key = productKey(productId);

        require(activeProducts[key], "Product not active");

        require(
            latestVersion[key] == expectedVersionId,
            "Expected version conflict"
        );

        return _commit(
            operationId,
            productId,
            Operation.UPDATE,
            canonicalPayload,
            suppliedDigest
        );
    }

    function deleteProduct(
        bytes32 operationId,
        string calldata productId,
        uint256 expectedVersionId
    )
        external
        onlyRole(WRITER)
        validProductId(productId)
        returns (uint256)
    {
        bytes32 key = productKey(productId);

        require(activeProducts[key], "Product not active");

        require(
            latestVersion[key] == expectedVersionId,
            "Expected version conflict"
        );

        // Tombstone: empty payload and its Keccak-256 digest.
        string memory emptyPayload = "";

        bytes32 emptyDigest = keccak256(bytes(emptyPayload));

        return _commit(
            operationId,
            productId,
            Operation.DELETE,
            emptyPayload,
            emptyDigest
        );
    }


    // ============================================================
    // 4. CURRENT PRODUCT READS
    // ============================================================

    function getLatestVersionId(
        string calldata productId
    ) external view returns (uint256) {
        return latestVersion[productKey(productId)];
    }

    function isProductActive(
        string calldata productId
    ) external view returns (bool) {
        return activeProducts[productKey(productId)];
    }

    function getCurrentProduct(
        string calldata productId
    )
        external
        view
        returns (
            bool active,
            ProductVersion memory version
        )
    {
        bytes32 key = productKey(productId);

        uint256 versionId = latestVersion[key];

        require(versionId != 0, "Unknown product");

        active = activeProducts[key];

        version = versions[versionId];
    }

    function getVersion(
        uint256 versionId
    ) external view returns (ProductVersion memory) {
        require(
            versionId > 0 && versionId < nextVersionId,
            "Unknown version"
        );

        return versions[versionId];
    }


    // ============================================================
    // 5. PAGINATED ENUMERATION
    // ============================================================

    function getProductCount()
        external
        view
        returns (uint256)
    {
        return productIds.length;
    }

    function getProductIds(
        uint256 offset,
        uint256 limit
    ) external view returns (string[] memory result) {

        require(limit > 0 && limit <= 100, "Invalid page size");

        if (offset >= productIds.length) {
            return new string[](0);
        }

        uint256 end = offset + limit;

        if (end > productIds.length) {
            end = productIds.length;
        }

        result = new string[](end - offset);

        for (uint256 i = offset; i < end; i++) {
            result[i - offset] = productIds[i];
        }
    }

    function getProductHistory(
        string calldata productId,
        uint256 offset,
        uint256 limit
    ) external view returns (uint256[] memory result) {

        require(limit > 0 && limit <= 100, "Invalid page size");

        uint256[] storage history =
            productHistory[productKey(productId)];

        if (offset >= history.length) {
            return new uint256[](0);
        }

        uint256 end = offset + limit;

        if (end > history.length) {
            end = history.length;
        }

        result = new uint256[](end - offset);

        for (uint256 i = offset; i < end; i++) {
            result[i - offset] = history[i];
        }
    }

    function getHistoryCount(
        string calldata productId
    ) external view returns (uint256) {
        return productHistory[productKey(productId)].length;
    }


    // ============================================================
    // 6. FULL-REBUILD INDEX CONFIGURATION
    // ============================================================

    uint256 public constant MAX_FILTERS_PER_CHUNK = 10;
    uint256 public constant MAX_SUMMARY_CHUNK_BYTES = 4096;
    uint256 public constant MAX_BITS = 1048576;

    struct IndexGeneration {
        uint256 expectedStateRevision;
        uint256 mBits;
        uint256 hashCount;
        uint256 targetFprPpm;
        uint256 expectedFilterCount;
        uint256 expectedSummaryLength;
        uint256 uploadedFilterCount;
        uint256 uploadedSummaryBytes;
        bool finalized;
    }

    struct FilterEntry {
        uint256 versionId;
        uint256 sourceBlockNumber;
        bytes packedBits;
        bool uploaded;
    }

    uint256 public nextGenerationId = 1;

    mapping(uint256 => IndexGeneration) private generations;

    mapping(
        uint256 => mapping(uint256 => FilterEntry)
    ) private generationFilters;

    // Prevent duplicate filter positions.
    mapping(
        uint256 => mapping(uint256 => bool)
    ) private filterPositionUploaded;

    // Prevent the same version appearing more than once.
    mapping(
        uint256 => mapping(uint256 => bool)
    ) private generationVersionUploaded;

    // Track individual summary bytes to prevent duplicate uploads.
    mapping(
        uint256 => mapping(uint256 => bool)
    ) private summaryByteUploaded;

    mapping(uint256 => bytes) private generationSummaries;

    uint256 public activeGenerationId;

    uint256 public publishedIndexRevision;

    event IndexGenerationStarted(
        uint256 indexed generationId,
        uint256 expectedStateRevision,
        uint256 expectedFilterCount,
        uint256 mBits,
        uint256 hashCount
    );

    event FilterChunkUploaded(
        uint256 indexed generationId,
        uint256 startIndex,
        uint256 itemCount
    );

    event SummaryChunkUploaded(
        uint256 indexed generationId,
        uint256 offset,
        uint256 byteCount
    );

    event IndexGenerationFinalized(
        uint256 indexed generationId,
        uint256 publishedRevision,
        uint256 publicationBlock
    );


    // ============================================================
    // 7. BEGIN INDEX GENERATION
    // ============================================================

    function beginIndexGeneration(
        uint256 expectedStateRevision,
        uint256 mBits,
        uint256 hashCount,
        uint256 targetFprPpm,
        uint256 expectedFilterCount,
        uint256 expectedSummaryLength
    )
        external
        onlyRole(INDEX_PUBLISHER)
        returns (uint256 generationId)
    {
        require(
            expectedStateRevision == stateRevision,
            "State revision mismatch"
        );

        require(
            mBits > 0 && mBits <= MAX_BITS,
            "Invalid mBits"
        );

        require(
            hashCount > 0 && hashCount <= 32,
            "Invalid hashCount"
        );

        require(
            expectedFilterCount == activeProductCount,
            "Active count mismatch"
        );

        require(
            expectedSummaryLength == (mBits + 7) / 8,
            "Invalid summary length"
        );

        require(
            targetFprPpm > 0 && targetFprPpm <= 1000000,
            "Invalid target FPR"
        );

        generationId = nextGenerationId++;

        generations[generationId] = IndexGeneration({
            expectedStateRevision: expectedStateRevision,
            mBits: mBits,
            hashCount: hashCount,
            targetFprPpm: targetFprPpm,
            expectedFilterCount: expectedFilterCount,
            expectedSummaryLength: expectedSummaryLength,
            uploadedFilterCount: 0,
            uploadedSummaryBytes: 0,
            finalized: false
        });

        generationSummaries[generationId] =
            new bytes(expectedSummaryLength);

        emit IndexGenerationStarted(
            generationId,
            expectedStateRevision,
            expectedFilterCount,
            mBits,
            hashCount
        );
    }


    // ============================================================
    // 8. UPLOAD FILTER CHUNKS
    // ============================================================

    function uploadFilterChunk(
        uint256 generationId,
        uint256 startIndex,
        uint256[] calldata versionIds,
        uint256[] calldata sourceBlockNumbers,
        bytes[] calldata packedFilters
    )
        external
        onlyRole(INDEX_PUBLISHER)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        IndexGeneration storage generation =
            generations[generationId];

        require(!generation.finalized, "Already finalized");

        require(
            stateRevision == generation.expectedStateRevision,
            "State changed during rebuild"
        );

        uint256 count = versionIds.length;

        require(count > 0, "Empty chunk");

        require(
            count <= MAX_FILTERS_PER_CHUNK,
            "Chunk too large"
        );

        require(
            sourceBlockNumbers.length == count &&
            packedFilters.length == count,
            "Array length mismatch"
        );

        require(
            startIndex + count <= generation.expectedFilterCount,
            "Chunk exceeds expected count"
        );

        for (uint256 i = 0; i < count; i++) {

            uint256 index = startIndex + i;
            uint256 versionId = versionIds[i];

            require(
                !filterPositionUploaded[generationId][index],
                "Duplicate filter position"
            );

            require(
                !generationVersionUploaded[generationId][versionId],
                "Duplicate version upload"
            );

            require(
                versionId > 0 && versionId < nextVersionId,
                "Invalid version ID"
            );

            ProductVersion storage version = versions[versionId];

            require(
                version.operation != Operation.DELETE,
                "Cannot index tombstone"
            );

            bytes32 key = productKey(version.productId);

            require(
                activeProducts[key] &&
                latestVersion[key] == versionId,
                "Version is not current"
            );

            require(
                version.sourceBlockNumber == sourceBlockNumbers[i],
                "Source block mismatch"
            );

            require(
                packedFilters[i].length == generation.expectedSummaryLength,
                "Invalid filter byte length"
            );

            generationFilters[generationId][index] =
                FilterEntry({
                    versionId: versionId,
                    sourceBlockNumber: sourceBlockNumbers[i],
                    packedBits: packedFilters[i],
                    uploaded: true
                });

            filterPositionUploaded[generationId][index] = true;

            generationVersionUploaded[generationId][versionId] = true;

            generation.uploadedFilterCount++;
        }

        emit FilterChunkUploaded(
            generationId,
            startIndex,
            count
        );
    }


    // ============================================================
    // 9. UPLOAD GLOBAL OR SUMMARY IN CHUNKS
    // ============================================================

    function uploadSummaryChunk(
        uint256 generationId,
        uint256 offset,
        bytes calldata chunk
    )
        external
        onlyRole(INDEX_PUBLISHER)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        IndexGeneration storage generation =
            generations[generationId];

        require(!generation.finalized, "Already finalized");

        require(
            stateRevision == generation.expectedStateRevision,
            "State changed during rebuild"
        );

        uint256 count = chunk.length;

        require(count > 0, "Empty summary chunk");

        require(
            count <= MAX_SUMMARY_CHUNK_BYTES,
            "Summary chunk too large"
        );

        require(
            offset + count <= generation.expectedSummaryLength,
            "Summary exceeds expected length"
        );

        bytes storage summary = generationSummaries[generationId];

        for (uint256 i = 0; i < count; i++) {

            uint256 position = offset + i;

            require(
                !summaryByteUploaded[generationId][position],
                "Duplicate summary byte"
            );

            summaryByteUploaded[generationId][position] = true;

            summary[position] = chunk[i];

            generation.uploadedSummaryBytes++;
        }

        emit SummaryChunkUploaded(
            generationId,
            offset,
            count
        );
    }


    // ============================================================
    // 10. FINALIZE GENERATION
    // ============================================================

    function finalizeIndexGeneration(
        uint256 generationId
    )
        external
        onlyRole(INDEX_PUBLISHER)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        IndexGeneration storage generation =
            generations[generationId];

        require(!generation.finalized, "Already finalized");

        require(
            stateRevision == generation.expectedStateRevision,
            "State changed before finalization"
        );

        require(
            generation.uploadedFilterCount ==
            generation.expectedFilterCount,
            "Incomplete filter upload"
        );

        require(
            generation.uploadedSummaryBytes ==
            generation.expectedSummaryLength,
            "Incomplete summary upload"
        );

        generation.finalized = true;

        activeGenerationId = generationId;

        publishedIndexRevision =
            generation.expectedStateRevision;

        emit IndexGenerationFinalized(
            generationId,
            publishedIndexRevision,
            block.number
        );
    }


    // ============================================================
    // 11. INDEX STATUS AND READS
    // ============================================================

    function isIndexFresh()
        external
        view
        returns (bool)
    {
        return (
            activeGenerationId != 0 &&
            publishedIndexRevision == stateRevision &&
            generations[activeGenerationId].finalized
        );
    }

    function getIndexStatus()
        external
        view
        returns (
            uint256 currentRevision,
            uint256 indexRevision,
            uint256 generationId,
            bool stale,
            uint256 activeCount
        )
    {
        currentRevision = stateRevision;

        indexRevision = publishedIndexRevision;

        generationId = activeGenerationId;

        activeCount = activeProductCount;

        stale = (
            generationId == 0 ||
            indexRevision != currentRevision
        );
    }

    function getGeneration(
        uint256 generationId
    )
        external
        view
        returns (IndexGeneration memory)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        return generations[generationId];
    }

    function getGenerationFilter(
        uint256 generationId,
        uint256 index
    )
        external
        view
        returns (
            uint256 versionId,
            uint256 sourceBlockNumber,
            bytes memory packedBits
        )
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        require(
            generations[generationId].finalized,
            "Generation incomplete"
        );

        require(
            index < generations[generationId].expectedFilterCount,
            "Index out of range"
        );

        FilterEntry storage entry =
            generationFilters[generationId][index];

        require(entry.uploaded, "Filter missing");

        return (
            entry.versionId,
            entry.sourceBlockNumber,
            entry.packedBits
        );
    }

    function getGenerationSummary(
        uint256 generationId
    )
        external
        view
        returns (bytes memory)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        require(
            generations[generationId].finalized,
            "Generation incomplete"
        );

        return generationSummaries[generationId];
    }

    function getGenerationFilterCount(
        uint256 generationId
    )
        external
        view
        returns (uint256)
    {
        require(
            generationId > 0 && generationId < nextGenerationId,
            "Unknown generation"
        );

        return generations[generationId].uploadedFilterCount;
    }
}
