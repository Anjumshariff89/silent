// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title LogAnchor - stores Merkle roots of security-log batches.
/// @notice An anchored root proves only that this commitment existed unchanged since the anchoring
///         block. It does NOT prove that any logged event actually happened.
contract LogAnchor {
    struct Anchor {
        bytes32 root;
        uint64 timestamp;
        address submitter;
    }

    address public immutable owner;
    uint256 public anchorCount;
    mapping(uint256 => Anchor) private anchors;

    event RootAnchored(uint256 indexed batchId, bytes32 indexed root, uint256 timestamp, address indexed submitter);

    error NotOwner();
    error EmptyRoot();
    error AlreadyAnchored(uint256 batchId);

    constructor() {
        owner = msg.sender;
    }

    /// @notice Anchor a batch root. Write-once per batchId: an anchored root can never be replaced.
    function anchorRoot(bytes32 root, uint256 batchId) external {
        if (msg.sender != owner) revert NotOwner();
        if (root == bytes32(0)) revert EmptyRoot();
        if (anchors[batchId].timestamp != 0) revert AlreadyAnchored(batchId);
        anchors[batchId] = Anchor(root, uint64(block.timestamp), msg.sender);
        anchorCount += 1;
        emit RootAnchored(batchId, root, block.timestamp, msg.sender);
    }

    function getAnchor(uint256 batchId) external view returns (bytes32 root, uint256 timestamp, address submitter) {
        Anchor memory a = anchors[batchId];
        return (a.root, a.timestamp, a.submitter);
    }

    function isAnchored(uint256 batchId) external view returns (bool) {
        return anchors[batchId].timestamp != 0;
    }
}
