import logging

import algokit_utils

logger = logging.getLogger(__name__)
MIN_DEPLOYER_SPENDING_BALANCE = algokit_utils.AlgoAmount(algo=2)


def _build_app_links(network_name: str, app_id: int, app_address: str) -> list[str]:
    links = [f"Frontend URL: http://localhost:5173"]

    # Lora supports application/account routes for localnet and public networks.
    links.append(f"App explorer: https://lora.algokit.io/{network_name}/application/{app_id}")
    links.append(f"App account: https://lora.algokit.io/{network_name}/account/{app_address}")
    return links


def _ensure_deployer_ready(
    algorand: algokit_utils.AlgorandClient,
    deployer: algokit_utils.SigningAccount,
) -> None:
    network = algorand.client.network()

    if network.is_localnet:
        dispenser = algorand.account.localnet_dispenser()
        algorand.account.ensure_funded(
            account_to_fund=deployer,
            dispenser_account=dispenser,
            min_spending_balance=MIN_DEPLOYER_SPENDING_BALANCE,
        )
        return

    account_info = algorand.account.get_information(deployer)
    spendable_balance = max(
        0,
        account_info.amount.micro_algo - account_info.min_balance.micro_algo,
    )
    required_balance = MIN_DEPLOYER_SPENDING_BALANCE.micro_algo

    if spendable_balance < required_balance:
        raise RuntimeError(
            "Deployment account is underfunded for app deployment. "
            f"Address: {deployer.address}. "
            f"Spendable balance: {spendable_balance} microALGO. "
            f"Required spendable balance: {required_balance} microALGO. "
            "Fund this exact account, or set DEPLOYER_MNEMONIC / DEPLOYER to the intended funded account."
        )
# define deployment behaviour based on supplied app spec
def deploy() -> None:
    from smart_contracts.artifacts.contract_main.expense_pool_contract_client import (
        CreateGroupArgs,
        ExpensePoolContractFactory,
        ExpensePoolContractMethodCallCreateParams,
        RegisterMembersArgs,
    )

    algorand = algokit_utils.AlgorandClient.from_environment()
    deployer_ = algorand.account.from_environment("DEPLOYER")
    _ensure_deployer_ready(algorand=algorand, deployer=deployer_)

    factory = ExpensePoolContractFactory(
        algorand=algorand,
        default_sender=deployer_.address,
        default_signer=deployer_.signer,
    )

    app_client, result = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
        create_params=ExpensePoolContractMethodCallCreateParams(
            args=CreateGroupArgs(
                group_name="Hackseries Group",
                member_addresses=[deployer_.address],
                approval_threshold=1,
            )
        ),
    )

    if result.operation_performed in [
        algokit_utils.OperationPerformed.Create,
        algokit_utils.OperationPerformed.Replace,
    ]:
        default_members = [deployer_.address]

        algorand.send.payment(
            algokit_utils.PaymentParams(
                amount=algokit_utils.AlgoAmount(algo=1),
                sender=deployer_.address,
                receiver=app_client.app_address,
            )
        )
        app_client.send.register_members(
            args=RegisterMembersArgs(member_addresses=default_members)
        )

    response = app_client.send.get_group_info()

    network = algorand.client.network()
    if network.is_localnet:
        network_name = "localnet"
    elif getattr(network, "is_testnet", False):
        network_name = "testnet"
    elif getattr(network, "is_mainnet", False):
        network_name = "mainnet"
    else:
        network_name = "unknown"
    links = _build_app_links(
        network_name=network_name,
        app_id=app_client.app_id,
        app_address=app_client.app_address,
    )

    logger.info("Deployment Summary")
    logger.info("------------------")
    logger.info(f"App name: {app_client.app_name}")
    logger.info(f"App ID: {app_client.app_id}")
    logger.info(f"App address: {app_client.app_address}")
    logger.info(f"Deployer address: {deployer_.address}")
    logger.info(f"Network: {network_name}")
    logger.info(f"Operation: {result.operation_performed}")
    logger.info(f"Group info: {response.abi_return}")
    for link in links:
        logger.info(link)
