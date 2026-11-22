// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

interface IProductLedgerC2B {
    enum Operation { INSERT, UPDATE, DELETE }

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
}

/**
 * Block-level C2 index.
 *
 * One contribution per blockchain block. A block's Bloom filter covers the
 * products recorded in that block that are STILL current in the ledger.
 *
 * The caller sends the block's NEW filter as bitmaps (main mask + summary
 * words). The contract diffs it against the stored bitmaps and writes ONLY
 * the counters whose value changes (0->1 / 1->0 transitions).
 *
 * Trust note: like the product-level experiment, the contract validates
 * membership against the ledger but does not recompute Bloom hashes on-chain;
 * the off-chain manager is verified against on-chain counters.
 */
contract C2BlockIncrementalExperiment {
    struct BlockEntry {
        bool active;
        uint256 productLedgerRevision;
        uint256 mainMask;
        uint256[] bitWords;
        bytes32[] members;
    }

    address public immutable writer;
    IProductLedgerC2B public immutable productLedger;
    uint256 public immutable mainSize;
    uint256 public immutable summarySize;
    uint256 public immutable blockCapacity;
    uint256 public immutable maxProductsPerBlock;
    uint256 public immutable wordCount;
    bytes32 public constant HASH_ALGORITHM_ID =
        keccak256("web3-keccak-double-hash-v1");

    uint256 public activeBlocks;
    uint256 public indexedProductCount;
    uint256 public stateRevision;
    uint256 public indexedProductLedgerRevision;

    mapping(uint256 => uint16) private mainCounters;
    mapping(uint256 => mapping(uint256 => uint16)) private summaryCounters;
    mapping(uint256 => BlockEntry) private blocks;
    mapping(bytes32 => uint256) public blockOfProductPlusOne;
    mapping(bytes32 => bool) public usedOperationIds;

    event BlockUpdated(
        bytes32 indexed operationId,
        uint256 indexed blockNumber,
        uint256 productLedgerRevision,
        uint256 stateRevision,
        uint256 added,
        uint256 removed,
        uint256 mainWrites,
        uint256 summaryWrites
    );
    event ProductLedgerSynchronized(uint256 productLedgerRevision, uint256 stateRevision);

    modifier onlyWriter() {
        require(msg.sender == writer, "Unauthorized writer");
        _;
    }

    constructor(
        address productLedger_,
        uint256 mainSize_,
        uint256 summarySize_,
        uint256 blockCapacity_,
        uint256 maxProductsPerBlock_,
        address writer_
    ) {
        require(productLedger_ != address(0), "Invalid product ledger");
        require(mainSize_ > 0 && mainSize_ <= 256, "Invalid main size");
        require(summarySize_ > 0 && summarySize_ <= 65536, "Invalid summary size");
        require(blockCapacity_ > 0 && blockCapacity_ <= type(uint16).max, "Invalid capacity");
        require(maxProductsPerBlock_ > 0 && maxProductsPerBlock_ <= 64, "Invalid block cap");
        require(writer_ != address(0), "Invalid writer");

        productLedger = IProductLedgerC2B(productLedger_);
        mainSize = mainSize_;
        summarySize = summarySize_;
        blockCapacity = blockCapacity_;
        maxProductsPerBlock = maxProductsPerBlock_;
        wordCount = (summarySize_ + 255) / 256;
        writer = writer_;
        indexedProductLedgerRevision = IProductLedgerC2B(productLedger_).stateRevision();
    }

    // ------------------------------------------------------------------
    // Write path
    // ------------------------------------------------------------------

    function updateBlock(
        bytes32 operationId,
        uint256 blockNumber,
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision,
        string[] calldata addedProductIds,
        string[] calldata removedProductIds,
        uint256 newMainMask,
        uint256[] calldata newBitWords
    ) external onlyWriter returns (uint256 mainWrites, uint256 summaryWrites) {
        require(stateRevision == expectedIndexRevision, "Index revision mismatch");
        require(
            productLedger.stateRevision() == expectedProductLedgerRevision,
            "Product ledger revision mismatch"
        );
        require(operationId != bytes32(0), "Empty operation ID");
        require(!usedOperationIds[operationId], "Operation already used");
        usedOperationIds[operationId] = true;
        require(addedProductIds.length + removedProductIds.length > 0, "No change");

        BlockEntry storage entry = blocks[blockNumber];

        for (uint256 i = 0; i < removedProductIds.length; i++) {
            _removeMember(entry, blockNumber, removedProductIds[i]);
        }
        for (uint256 i = 0; i < addedProductIds.length; i++) {
            _addMember(entry, blockNumber, addedProductIds[i]);
        }

        uint256 memberCount = entry.members.length;
        require(memberCount <= maxProductsPerBlock, "Block product cap exceeded");

        bool willBeActive = memberCount > 0;
        if (!entry.active && willBeActive) {
            require(activeBlocks < blockCapacity, "Capacity exceeded");
        }
        _validateMasks(willBeActive, newMainMask, newBitWords);

        (mainWrites, summaryWrites) = _applyDelta(entry, newMainMask, newBitWords);

        if (!entry.active && willBeActive) activeBlocks++;
        if (entry.active && !willBeActive) activeBlocks--;
        entry.active = willBeActive;
        entry.productLedgerRevision = expectedProductLedgerRevision;
        indexedProductCount =
            indexedProductCount + addedProductIds.length - removedProductIds.length;

        stateRevision++;
        emit BlockUpdated(
            operationId,
            blockNumber,
            expectedProductLedgerRevision,
            stateRevision,
            addedProductIds.length,
            removedProductIds.length,
            mainWrites,
            summaryWrites
        );
    }

    function synchronizeProductLedger(
        uint256 expectedIndexRevision,
        uint256 expectedProductLedgerRevision
    ) external onlyWriter {
        require(stateRevision == expectedIndexRevision, "Index revision mismatch");
        require(
            productLedger.stateRevision() == expectedProductLedgerRevision,
            "Product ledger revision mismatch"
        );
        require(
            indexedProductCount == productLedger.activeProductCount(),
            "Active product count mismatch"
        );
        indexedProductLedgerRevision = expectedProductLedgerRevision;
        stateRevision++;
        emit ProductLedgerSynchronized(expectedProductLedgerRevision, stateRevision);
    }

    // ------------------------------------------------------------------
    // Membership validation against the authoritative ledger
    // ------------------------------------------------------------------

    function _addMember(
        BlockEntry storage entry,
        uint256 blockNumber,
        string calldata productId
    ) private {
        bytes32 key = productLedger.productKey(productId);
        require(blockOfProductPlusOne[key] == 0, "Product already indexed");
        (bool active, IProductLedgerC2B.ProductVersion memory version) =
            productLedger.getCurrentProduct(productId);
        require(active, "Product is not active");
        require(version.sourceBlockNumber == blockNumber, "Product not in this block");
        require(keccak256(bytes(version.productId)) == key, "Product identity mismatch");
        entry.members.push(key);
        blockOfProductPlusOne[key] = blockNumber + 1;
    }

    function _removeMember(
        BlockEntry storage entry,
        uint256 blockNumber,
        string calldata productId
    ) private {
        bytes32 key = productLedger.productKey(productId);
        require(blockOfProductPlusOne[key] == blockNumber + 1, "Product not indexed in block");
        (bool active, IProductLedgerC2B.ProductVersion memory version) =
            productLedger.getCurrentProduct(productId);
        require(
            !active || version.sourceBlockNumber != blockNumber,
            "Product still current in block"
        );

        uint256 length = entry.members.length;
        for (uint256 i = 0; i < length; i++) {
            if (entry.members[i] == key) {
                entry.members[i] = entry.members[length - 1];
                entry.members.pop();
                blockOfProductPlusOne[key] = 0;
                return;
            }
        }
        revert("Member missing");
    }

    function _validateMasks(
        bool willBeActive,
        uint256 mainMask,
        uint256[] calldata words
    ) private view {
        require(words.length == wordCount, "Invalid word count");
        uint256 any = mainMask;
        for (uint256 w = 0; w < words.length; w++) {
            any |= words[w];
        }
        if (!willBeActive) {
            require(any == 0, "Empty block must have empty filter");
            return;
        }
        require(mainMask != 0, "Empty main mask");
        if (mainSize < 256) {
            require(mainMask >> mainSize == 0, "Main position out of range");
        }
        uint256 tail = summarySize % 256;
        if (tail != 0) {
            require(words[words.length - 1] >> tail == 0, "Summary position out of range");
        }
        uint256 bitsAny;
        for (uint256 w = 0; w < words.length; w++) bitsAny |= words[w];
        require(bitsAny != 0, "Empty summary filter");
    }

    // ------------------------------------------------------------------
    // Delta engine: only changed counters are written
    // ------------------------------------------------------------------

    function _applyDelta(
        BlockEntry storage entry,
        uint256 newMain,
        uint256[] calldata newWords
    ) private returns (uint256 mainWrites, uint256 summaryWrites) {
        uint256 oldMain = entry.active ? entry.mainMask : 0;
        uint256[] memory oldWords = entry.bitWords.length == 0
            ? new uint256[](wordCount)
            : entry.bitWords;
        uint256 union = oldMain | newMain;

        for (uint256 p = 0; p < mainSize; p++) {
            uint256 flag = uint256(1) << p;
            if (union & flag == 0) continue;
            bool inOld = oldMain & flag != 0;
            bool inNew = newMain & flag != 0;

            if (inOld && !inNew) {
                require(mainCounters[p] > 0, "Main counter underflow");
                mainCounters[p]--;
                mainWrites++;
            } else if (inNew && !inOld) {
                mainCounters[p]++;
                mainWrites++;
            }

            for (uint256 w = 0; w < wordCount; w++) {
                uint256 ow = inOld ? oldWords[w] : 0;
                uint256 nw = inNew ? newWords[w] : 0;
                uint256 diff = ow ^ nw;
                while (diff != 0) {
                    uint256 lowest = diff & (~diff + 1);
                    uint256 bit = w * 256 + _bitIndex(lowest);
                    if (nw & lowest != 0) {
                        summaryCounters[p][bit]++;
                    } else {
                        require(summaryCounters[p][bit] > 0, "Summary counter underflow");
                        summaryCounters[p][bit]--;
                    }
                    summaryWrites++;
                    diff &= diff - 1;
                }
            }
        }

        // Persist the new bitmaps (write a word only if it changed).
        if (entry.bitWords.length == 0) {
            for (uint256 w = 0; w < wordCount; w++) entry.bitWords.push(newWords[w]);
        } else {
            for (uint256 w = 0; w < wordCount; w++) {
                if (entry.bitWords[w] != newWords[w]) entry.bitWords[w] = newWords[w];
            }
        }
        if (entry.mainMask != newMain) entry.mainMask = newMain;
    }

    /// Index of the single set bit in `x` (x must be a power of two).
    function _bitIndex(uint256 x) private pure returns (uint256 r) {
        if (x >> 128 != 0) { r += 128; x >>= 128; }
        if (x >> 64 != 0) { r += 64; x >>= 64; }
        if (x >> 32 != 0) { r += 32; x >>= 32; }
        if (x >> 16 != 0) { r += 16; x >>= 16; }
        if (x >> 8 != 0) { r += 8; x >>= 8; }
        if (x >> 4 != 0) { r += 4; x >>= 4; }
        if (x >> 2 != 0) { r += 2; x >>= 2; }
        if (x >> 1 != 0) { r += 1; }
    }

    // ------------------------------------------------------------------
    // Reads
    // ------------------------------------------------------------------

    function isFresh() external view returns (bool) {
        return
            indexedProductLedgerRevision == productLedger.stateRevision() &&
            indexedProductCount == productLedger.activeProductCount();
    }

    function getMainCount(uint256 position) external view returns (uint16) {
        require(position < mainSize, "Main position out of range");
        return mainCounters[position];
    }

    function getMainCounts() external view returns (uint16[] memory counts) {
        counts = new uint16[](mainSize);
        for (uint256 i = 0; i < mainSize; i++) counts[i] = mainCounters[i];
    }

    function getSummaryCount(uint256 mainPosition, uint256 bitPosition)
        external view returns (uint16)
    {
        require(mainPosition < mainSize, "Main position out of range");
        require(bitPosition < summarySize, "Summary position out of range");
        return summaryCounters[mainPosition][bitPosition];
    }

    function getSummaryCountsAt(
        uint256[] calldata mainPositions,
        uint256[] calldata summaryBits
    ) external view returns (uint16[] memory counts) {
        require(mainPositions.length > 0 && summaryBits.length > 0, "Empty selection");
        for (uint256 j = 0; j < summaryBits.length; j++) {
            require(summaryBits[j] < summarySize, "Summary position out of range");
        }
        counts = new uint16[](mainPositions.length * summaryBits.length);
        for (uint256 i = 0; i < mainPositions.length; i++) {
            require(mainPositions[i] < mainSize, "Main position out of range");
            for (uint256 j = 0; j < summaryBits.length; j++) {
                counts[i * summaryBits.length + j] =
                    summaryCounters[mainPositions[i]][summaryBits[j]];
            }
        }
    }

    function getBlock(uint256 blockNumber) external view returns (
        bool active,
        uint256 productLedgerRevision,
        uint256 mainMask,
        uint256[] memory bitWords,
        bytes32[] memory members
    ) {
        BlockEntry storage e = blocks[blockNumber];
        return (e.active, e.productLedgerRevision, e.mainMask, e.bitWords, e.members);
    }
}