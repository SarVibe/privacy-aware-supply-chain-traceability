// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

interface IProductLedgerC2 {
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

    function stateRevision() external view returns (uint256);
    function activeProductCount() external view returns (uint256);
    function productKey(string memory productId) external pure returns (bytes32);
    function getCurrentProduct(
        string calldata productId
    ) external view returns (bool active, ProductVersion memory version);
    function getVersion(uint256 versionId) external view returns (ProductVersion memory);
}

contract C2IncrementalExperiment {
    struct Contribution {
        bool active;
        bytes32 productKey;
        uint256 versionId;
        uint256 sourceBlockNumber;
        bytes32 payloadDigest;
        uint256 productLedgerRevision;
        uint8[] mainPositions;
        uint16[] summaryBits;
    }

    address public immutable writer;
    IProductLedgerC2 public immutable productLedger;
    uint256 public immutable mainSize;
    uint256 public immutable summarySize;
    uint256 public immutable capacity;
    uint8 public immutable mainHashCount;
    uint8 public immutable summaryHashCount;
    bytes32 public constant HASH_ALGORITHM_ID =
        keccak256("web3-keccak-double-hash-v1");

    uint256 public activeCount;
    uint256 public stateRevision;
    uint256 public indexedProductLedgerRevision;

    mapping(uint256 => uint16) private mainCounters;
    mapping(uint256 => mapping(uint256 => uint16)) private summaryCounters;
    mapping(bytes32 => Contribution) private contributions;
    mapping(bytes32 => bytes32) public contributionByProduct;
    mapping(bytes32 => bool) public usedOperationIds;

    event ContributionAdded(
        bytes32 indexed operationId,
        bytes32 indexed contributionId,
        bytes32 indexed productKey,
        uint256 versionId,
        bytes32 payloadDigest,
        uint256 productLedgerRevision,
        uint256 stateRevision
    );
    event ContributionRemoved(
        bytes32 indexed operationId,
        bytes32 indexed contributionId,
        bytes32 indexed productKey,
        uint256 productLedgerRevision,
        uint256 stateRevision
    );
    event ContributionReplaced(
        bytes32 indexed operationId,
        bytes32 indexed contributionId,
        bytes32 indexed productKey,
        uint256 versionId,
        bytes32 payloadDigest,
        uint256 productLedgerRevision,
        uint256 stateRevision
    );
    event ProductLedgerSynchronized(
        uint256 productLedgerRevision,
        uint256 stateRevision
    );

    modifier onlyWriter() {
        require(msg.sender == writer, "Unauthorized writer");
        _;
    }

    constructor(
        address productLedger_,
        uint256 mainSize_,
        uint256 summarySize_,
        uint256 capacity_,
        uint8 mainHashCount_,
        uint8 summaryHashCount_,
        address writer_
    ) {
        require(productLedger_ != address(0), "Invalid product ledger");
        require(mainSize_ > 0 && mainSize_ <= 256, "Invalid main size");
        require(summarySize_ > 0 && summarySize_ <= 65536, "Invalid summary size");
        require(capacity_ > 0 && capacity_ <= type(uint16).max, "Invalid capacity");
        require(mainHashCount_ > 0, "Invalid main hash count");
        require(summaryHashCount_ > 0, "Invalid summary hash count");
        require(writer_ != address(0), "Invalid writer");

        productLedger = IProductLedgerC2(productLedger_);
        mainSize = mainSize_;
        summarySize = summarySize_;
        capacity = capacity_;
        mainHashCount = mainHashCount_;
        summaryHashCount = summaryHashCount_;
        writer = writer_;
        indexedProductLedgerRevision = IProductLedgerC2(productLedger_).stateRevision();
    }

    function addContribution(
        bytes32 operationId,
        bytes32 contributionId,
        string calldata productId,
        bytes32 productKey,
        uint256 versionId,
        uint256 sourceBlockNumber,
        bytes32 payloadDigest,
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision,
        uint8[] calldata selectedMainPositions,
        uint16[] calldata setSummaryBits
    ) external onlyWriter {
        _checkRevisions(expectedIndexRevision, expectedProductLedgerRevision);
        require(
            contributionId == _contributionId(productId),
            "Invalid contribution ID"
        );
        _validateCurrentProduct(
            productId,
            productKey,
            versionId,
            sourceBlockNumber,
            payloadDigest
        );
        _consumeOperation(operationId);
        _add(
            contributionId,
            productKey,
            versionId,
            sourceBlockNumber,
            payloadDigest,
            expectedProductLedgerRevision,
            selectedMainPositions,
            setSummaryBits
        );
        stateRevision++;
        emit ContributionAdded(
            operationId,
            contributionId,
            productKey,
            versionId,
            payloadDigest,
            expectedProductLedgerRevision,
            stateRevision
        );
    }

    function removeContribution(
        bytes32 operationId,
        bytes32 contributionId,
        string calldata productId,
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision
    ) external onlyWriter {
        _checkRevisions(expectedIndexRevision, expectedProductLedgerRevision);
        Contribution storage current = contributions[contributionId];
        require(current.active, "Unknown contribution");
        require(
            contributionId == _contributionId(productId),
            "Invalid contribution ID"
        );
        _validateDeletedProduct(productId, current);
        _consumeOperation(operationId);
        bytes32 productKey = _remove(contributionId);
        stateRevision++;
        emit ContributionRemoved(
            operationId,
            contributionId,
            productKey,
            expectedProductLedgerRevision,
            stateRevision
        );
    }

    function replaceContribution(
        bytes32 operationId,
        bytes32 contributionId,
        string calldata productId,
        uint256 versionId,
        uint256 sourceBlockNumber,
        bytes32 payloadDigest,
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision,
        uint8[] calldata selectedMainPositions,
        uint16[] calldata setSummaryBits
    ) external onlyWriter {
        _checkRevisions(expectedIndexRevision, expectedProductLedgerRevision);
        Contribution storage current = contributions[contributionId];
        require(current.active, "Unknown contribution");
        require(
            contributionId == _contributionId(productId),
            "Invalid contribution ID"
        );
        _validateHistoricalContribution(productId, current);
        _validateCurrentProduct(
            productId,
            current.productKey,
            versionId,
            sourceBlockNumber,
            payloadDigest
        );
        _consumeOperation(operationId);
        bytes32 productKey = _remove(contributionId);
        require(productKey == current.productKey, "Product key mismatch");
        _add(
            contributionId,
            productKey,
            versionId,
            sourceBlockNumber,
            payloadDigest,
            expectedProductLedgerRevision,
            selectedMainPositions,
            setSummaryBits
        );
        stateRevision++;
        emit ContributionReplaced(
            operationId,
            contributionId,
            productKey,
            versionId,
            payloadDigest,
            expectedProductLedgerRevision,
            stateRevision
        );
    }

    function synchronizeProductLedger(
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision
    ) external onlyWriter {
        _checkRevisions(expectedIndexRevision, expectedProductLedgerRevision);
        require(
            activeCount == productLedger.activeProductCount(),
            "Active product count mismatch"
        );
        indexedProductLedgerRevision = expectedProductLedgerRevision;
        stateRevision++;
        emit ProductLedgerSynchronized(
            expectedProductLedgerRevision,
            stateRevision
        );
    }

    function isFresh() external view returns (bool) {
        return
            indexedProductLedgerRevision == productLedger.stateRevision() &&
            activeCount == productLedger.activeProductCount();
    }

    function getMainCount(uint256 position) external view returns (uint16) {
        require(position < mainSize, "Main position out of range");
        return mainCounters[position];
    }

    function getMainCounts() external view returns (uint16[] memory counts) {
        counts = new uint16[](mainSize);
        for (uint256 i = 0; i < mainSize; i++) {
            counts[i] = mainCounters[i];
        }
    }

    function getSummaryCount(
        uint256 mainPosition,
        uint256 bitPosition
    ) external view returns (uint16) {
        require(mainPosition < mainSize, "Main position out of range");
        require(bitPosition < summarySize, "Summary position out of range");
        return summaryCounters[mainPosition][bitPosition];
    }

    function getSummaryCounts(
        uint256 mainPosition
    ) external view returns (uint16[] memory counts) {
        require(mainPosition < mainSize, "Main position out of range");
        counts = new uint16[](summarySize);
        for (uint256 i = 0; i < summarySize; i++) {
            counts[i] = summaryCounters[mainPosition][i];
        }
    }

    function getSummaryCountsRange(
        uint256 startMainPosition,
        uint256 mainPositionCount
    ) external view returns (uint16[] memory counts) {
        require(
            mainPositionCount > 0 &&
                startMainPosition + mainPositionCount <= mainSize,
            "Main position range out of range"
        );
        counts = new uint16[](mainPositionCount * summarySize);
        for (uint256 row = 0; row < mainPositionCount; row++) {
            for (uint256 bit = 0; bit < summarySize; bit++) {
                counts[row * summarySize + bit] =
                    summaryCounters[startMainPosition + row][bit];
            }
        }
    }

    function getContribution(
        bytes32 contributionId
    )
        external
        view
        returns (
            bool active,
            bytes32 productKey,
            uint256 versionId,
            uint256 sourceBlockNumber,
            bytes32 payloadDigest,
            uint256 productLedgerRevision,
            uint8[] memory selectedMainPositions,
            uint16[] memory setSummaryBits
        )
    {
        Contribution storage contribution = contributions[contributionId];
        return (
            contribution.active,
            contribution.productKey,
            contribution.versionId,
            contribution.sourceBlockNumber,
            contribution.payloadDigest,
            contribution.productLedgerRevision,
            contribution.mainPositions,
            contribution.summaryBits
        );
    }

    function _checkRevisions(
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision
    ) private view {
        require(stateRevision == expectedIndexRevision, "Index revision mismatch");
        require(
            productLedger.stateRevision() == expectedProductLedgerRevision,
            "Product ledger revision mismatch"
        );
    }

    function _consumeOperation(bytes32 operationId) private {
        require(operationId != bytes32(0), "Empty operation ID");
        require(!usedOperationIds[operationId], "Operation already used");
        usedOperationIds[operationId] = true;
    }

    function _contributionId(
        string calldata productId
    ) private pure returns (bytes32) {
        return keccak256(abi.encodePacked("c2:", productId));
    }

    function _validateCurrentProduct(
        string calldata productId,
        bytes32 productKey,
        uint256 versionId,
        uint256 sourceBlockNumber,
        bytes32 payloadDigest
    ) private view {
        require(
            productLedger.productKey(productId) == productKey,
            "Product key mismatch"
        );
        (bool active, IProductLedgerC2.ProductVersion memory version) =
            productLedger.getCurrentProduct(productId);
        require(active, "Product is not active");
        require(version.versionId == versionId, "Product version mismatch");
        require(keccak256(bytes(version.productId)) == productKey, "Product identity mismatch");
        require(version.sourceBlockNumber == sourceBlockNumber, "Source block mismatch");
        require(version.payloadDigest == payloadDigest, "Payload digest mismatch");
    }

    function _validateDeletedProduct(
        string calldata productId,
        Contribution storage contribution
    ) private view {
        require(
            productLedger.productKey(productId) == contribution.productKey,
            "Product key mismatch"
        );
        (bool active, IProductLedgerC2.ProductVersion memory version) =
            productLedger.getCurrentProduct(productId);
        require(!active, "Product is still active");
        require(
            keccak256(bytes(version.productId)) == contribution.productKey,
            "Product identity mismatch"
        );
        require(version.operation == IProductLedgerC2.Operation.DELETE, "Product not deleted");
        IProductLedgerC2.ProductVersion memory previous =
            productLedger.getVersion(contribution.versionId);
        require(
            keccak256(bytes(previous.productId)) == contribution.productKey,
            "Product identity mismatch"
        );
        require(previous.payloadDigest == contribution.payloadDigest, "Payload digest mismatch");
        require(
            previous.sourceBlockNumber == contribution.sourceBlockNumber,
            "Source block mismatch"
        );
    }

    function _validateHistoricalContribution(
        string calldata productId,
        Contribution storage contribution
    ) private view {
        require(
            productLedger.productKey(productId) == contribution.productKey,
            "Product key mismatch"
        );
        IProductLedgerC2.ProductVersion memory previous =
            productLedger.getVersion(contribution.versionId);
        require(
            keccak256(bytes(previous.productId)) == contribution.productKey,
            "Product identity mismatch"
        );
        require(previous.payloadDigest == contribution.payloadDigest, "Payload digest mismatch");
        require(
            previous.sourceBlockNumber == contribution.sourceBlockNumber,
            "Source block mismatch"
        );
    }

    function _validatePositions(
        uint8[] calldata selectedMainPositions,
        uint16[] calldata setSummaryBits
    ) private view {
        require(
            selectedMainPositions.length > 0 &&
                selectedMainPositions.length <= mainSize,
            "Invalid main positions"
        );
        require(
            setSummaryBits.length > 0 && setSummaryBits.length <= summarySize,
            "Invalid summary bits"
        );

        for (uint256 i = 0; i < selectedMainPositions.length; i++) {
            require(selectedMainPositions[i] < mainSize, "Main position out of range");
            for (uint256 j = 0; j < i; j++) {
                require(
                    selectedMainPositions[i] != selectedMainPositions[j],
                    "Duplicate main position"
                );
            }
        }

        for (uint256 i = 0; i < setSummaryBits.length; i++) {
            require(setSummaryBits[i] < summarySize, "Summary position out of range");
            for (uint256 j = 0; j < i; j++) {
                require(setSummaryBits[i] != setSummaryBits[j], "Duplicate summary bit");
            }
        }
    }

    function _add(
        bytes32 contributionId,
        bytes32 productKey,
        uint256 versionId,
        uint256 sourceBlockNumber,
        bytes32 payloadDigest,
        uint256 productLedgerRevision,
        uint8[] calldata selectedMainPositions,
        uint16[] calldata setSummaryBits
    ) private {
        require(contributionId != bytes32(0), "Empty contribution ID");
        require(productKey != bytes32(0), "Empty product key");
        require(versionId > 0, "Invalid version ID");

        Contribution storage contribution = contributions[contributionId];
        require(!contribution.active, "Contribution already active");
        require(contributionByProduct[productKey] == bytes32(0), "Product already active");
        require(activeCount < capacity, "Capacity exceeded");
        _validatePositions(selectedMainPositions, setSummaryBits);

        contribution.active = true;
        contribution.productKey = productKey;
        contribution.versionId = versionId;
        contribution.sourceBlockNumber = sourceBlockNumber;
        contribution.payloadDigest = payloadDigest;
        contribution.productLedgerRevision = productLedgerRevision;
        contributionByProduct[productKey] = contributionId;
        activeCount++;

        for (uint256 i = 0; i < selectedMainPositions.length; i++) {
            uint256 mainPosition = selectedMainPositions[i];
            mainCounters[mainPosition]++;
            contribution.mainPositions.push(selectedMainPositions[i]);

            for (uint256 j = 0; j < setSummaryBits.length; j++) {
                uint256 bitPosition = setSummaryBits[j];
                summaryCounters[mainPosition][bitPosition]++;
            }
        }

        for (uint256 i = 0; i < setSummaryBits.length; i++) {
            contribution.summaryBits.push(setSummaryBits[i]);
        }
    }

    function _remove(bytes32 contributionId) private returns (bytes32 productKey) {
        Contribution storage contribution = contributions[contributionId];
        require(contribution.active, "Unknown contribution");
        productKey = contribution.productKey;

        for (uint256 i = 0; i < contribution.mainPositions.length; i++) {
            uint256 mainPosition = contribution.mainPositions[i];
            require(mainCounters[mainPosition] > 0, "Main counter underflow");
            for (uint256 j = 0; j < contribution.summaryBits.length; j++) {
                uint256 bitPosition = contribution.summaryBits[j];
                require(
                    summaryCounters[mainPosition][bitPosition] > 0,
                    "Summary counter underflow"
                );
                summaryCounters[mainPosition][bitPosition]--;
            }
            mainCounters[mainPosition]--;
        }

        contribution.active = false;
        contributionByProduct[productKey] = bytes32(0);
        activeCount--;
        delete contribution.mainPositions;
        delete contribution.summaryBits;
    }
}
