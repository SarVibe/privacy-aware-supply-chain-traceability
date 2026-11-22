from app.blockchain.contract import get_contract
from app.blockchain.transactions import send_transaction
from app.blockchain.wallet import get_wallet


def grant_index_publisher_role() -> dict:
    _, contract = get_contract()
    wallet = get_wallet()

    admin_role = contract.functions.ADMIN().call()
    publisher_role = contract.functions.INDEX_PUBLISHER().call()

    if not contract.functions.hasRole(
        admin_role, wallet.address
    ).call():
        raise PermissionError(
            "Current wallet does not have ADMIN role"
        )

    if contract.functions.hasRole(
        publisher_role, wallet.address
    ).call():
        return {
            "granted": False,
            "message": "INDEX_PUBLISHER role already exists",
        }

    transaction = contract.functions.grantRole(
        publisher_role,
        wallet.address,
    )

    receipt = send_transaction(transaction)

    return {
        "granted": receipt.status == 1,
        "wallet": wallet.address,
        "transaction_hash": receipt.transactionHash.hex(),
        "block_number": receipt.blockNumber,
    }