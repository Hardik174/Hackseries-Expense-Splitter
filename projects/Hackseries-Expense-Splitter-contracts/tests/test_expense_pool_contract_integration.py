from urllib.error import URLError

import algokit_utils
import pytest

from smart_contracts.artifacts.contract_main.expense_pool_contract_client import (
    AddExpenseArgs,
    ApproveExpenseArgs,
    CreateGroupArgs,
    DepositToPoolArgs,
    ExpensePoolContractClient,
    ExpensePoolContractFactory,
    ExpensePoolContractMethodCallCreateParams,
    RegisterMembersArgs,
    SettleExpenseArgs,
)

DEFAULT_GROUP_NAME = "Test Group"
DEFAULT_DEPOSIT_AMOUNT = 600_000
DEFAULT_EXPENSE_AMOUNT = 100_000


def _account_balance(
    algorand: algokit_utils.AlgorandClient,
    account: algokit_utils.SigningAccount,
) -> int:
    return algorand.account.get_information(account).amount.micro_algo


def _fund_account(
    algorand: algokit_utils.AlgorandClient,
    account: algokit_utils.SigningAccount,
    dispenser: algokit_utils.SigningAccount,
) -> None:
    algorand.account.ensure_funded(
        account_to_fund=account,
        dispenser_account=dispenser,
        min_spending_balance=algokit_utils.AlgoAmount(algo=5),
    )


def _deploy_group(
    algorand: algokit_utils.AlgorandClient,
    creator: algokit_utils.SigningAccount,
    members: list[algokit_utils.SigningAccount],
    threshold: int,
) -> ExpensePoolContractClient:
    factory = ExpensePoolContractFactory(
        algorand=algorand,
        default_sender=creator.address,
        default_signer=creator.signer,
    )

    app_client, _ = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
        create_params=ExpensePoolContractMethodCallCreateParams(
            args=CreateGroupArgs(
                group_name=DEFAULT_GROUP_NAME,
                member_addresses=[m.address for m in members],
                approval_threshold=threshold,
            )
        ),
    )

    algorand.send.payment(
        algokit_utils.PaymentParams(
            amount=algokit_utils.AlgoAmount(algo=1),
            sender=creator.address,
            signer=creator.signer,
            receiver=app_client.app_address,
        )
    )

    app_client.send.register_members(
        args=RegisterMembersArgs(member_addresses=[m.address for m in members]),
        params=algokit_utils.CommonAppCallParams(
            sender=creator.address,
            signer=creator.signer,
        ),
    )

    return app_client


def _deposit(
    algorand: algokit_utils.AlgorandClient,
    app_client,
    sender: algokit_utils.SigningAccount,
    amount_micro_algo: int,
    *,
    payment_sender: algokit_utils.SigningAccount | None = None,
    receiver: str | None = None,
) -> None:
    payment_sender = payment_sender or sender
    pay_txn = algorand.create_transaction.payment(
        algokit_utils.PaymentParams(
            sender=payment_sender.address,
            signer=payment_sender.signer,
            receiver=receiver or app_client.app_address,
            amount=algokit_utils.AlgoAmount(micro_algo=amount_micro_algo),
        )
    )

    app_client.send.deposit_to_pool(
        args=DepositToPoolArgs(pay_txn=pay_txn),
        params=algokit_utils.CommonAppCallParams(
            sender=sender.address,
            signer=sender.signer,
        ),
        send_params=algokit_utils.SendParams(populate_app_call_resources=True),
    )


def _app_call_params(account: algokit_utils.SigningAccount) -> algokit_utils.CommonAppCallParams:
    return algokit_utils.CommonAppCallParams(sender=account.address, signer=account.signer)


def _send_params() -> algokit_utils.SendParams:
    return algokit_utils.SendParams(populate_app_call_resources=True)


def _settle_params(account: algokit_utils.SigningAccount) -> algokit_utils.CommonAppCallParams:
    # settle_expense emits one inner payment transaction; cover that fee from the outer app call.
    return algokit_utils.CommonAppCallParams(
        sender=account.address,
        signer=account.signer,
        extra_fee=algokit_utils.AlgoAmount(micro_algo=1_000),
    )


@pytest.fixture
def localnet_setup():
    algorand = algokit_utils.AlgorandClient.default_localnet()
    try:
        dispenser = algorand.account.localnet_dispenser()
    except Exception as ex:
        if isinstance(ex, URLError) or "Connection refused" in str(ex) or "WinError 10061" in str(ex):
            pytest.skip("LocalNet is not running; start it with `algokit localnet start`.")
        raise

    creator = algorand.account.random()
    member_b = algorand.account.random()
    member_c = algorand.account.random()
    outsider = algorand.account.random()

    _fund_account(algorand, creator, dispenser)
    _fund_account(algorand, member_b, dispenser)
    _fund_account(algorand, member_c, dispenser)
    _fund_account(algorand, outsider, dispenser)

    return algorand, creator, member_b, member_c, outsider


def test_full_happy_path_create_deposit_add_approve_settle(localnet_setup):
    algorand, creator, member_b, member_c, _ = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b, member_c],
        threshold=2,
    )

    _deposit(algorand, app_client, creator, DEFAULT_DEPOSIT_AMOUNT)

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=DEFAULT_EXPENSE_AMOUNT, description="Dinner"),
        params=_app_call_params(member_b),
        send_params=_send_params(),
    )

    balance_before_settle = _account_balance(algorand, member_b)

    app_client.send.approve_expense(
        args=ApproveExpenseArgs(expense_id=1),
        params=_app_call_params(member_c),
        send_params=_send_params(),
    )

    app_client.send.settle_expense(
        args=SettleExpenseArgs(expense_id=1),
        params=_settle_params(creator),
        send_params=_send_params(),
    )

    group_info = app_client.send.get_group_info(
        send_params=_send_params()
    ).abi_return
    expense_info = app_client.send.get_expense_info(
        args=(1,),
        send_params=_send_params(),
    ).abi_return
    expense_state = app_client.state.box.expenses.get_value(1)

    assert group_info is not None
    assert expense_info is not None
    assert expense_state is not None

    assert group_info[0] == DEFAULT_GROUP_NAME
    assert group_info[1] == 3
    assert group_info[2] == 2
    assert group_info[3] == DEFAULT_DEPOSIT_AMOUNT - DEFAULT_EXPENSE_AMOUNT
    assert group_info[4] == 1

    global_state = app_client.state.global_state
    assert global_state is not None
    assert global_state.pool_balance == DEFAULT_DEPOSIT_AMOUNT - DEFAULT_EXPENSE_AMOUNT
    assert global_state.expense_count == 1

    assert expense_info[0] == member_b.address
    assert expense_info[1] == DEFAULT_EXPENSE_AMOUNT
    assert expense_info[2] == "Dinner"
    assert expense_info[3] == 2
    assert expense_info[4] is True
    assert expense_state.payer == member_b.address
    assert expense_state.amount == DEFAULT_EXPENSE_AMOUNT
    assert expense_state.approval_count == 2
    assert expense_state.settled is True
    assert _account_balance(algorand, member_b) == balance_before_settle + DEFAULT_EXPENSE_AMOUNT


def test_two_member_threshold_flow(localnet_setup):
    algorand, creator, member_b, _, _ = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    _deposit(algorand, app_client, creator, 250_000)

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=75_000, description="Taxi"),
        params=_app_call_params(member_b),
        send_params=_send_params(),
    )

    app_client.send.approve_expense(
        args=ApproveExpenseArgs(expense_id=1),
        params=_app_call_params(creator),
        send_params=_send_params(),
    )

    app_client.send.settle_expense(
        args=SettleExpenseArgs(expense_id=1),
        params=_settle_params(creator),
        send_params=_send_params(),
    )

    expense_state = app_client.state.box.expenses.get_value(1)
    global_state = app_client.state.global_state

    assert expense_state is not None
    assert global_state is not None
    assert expense_state.approval_count == 2
    assert expense_state.settled is True
    assert global_state.member_count == 2
    assert global_state.approval_threshold == 2
    assert global_state.pool_balance == 175_000
    assert global_state.expense_count == 1


@pytest.mark.parametrize(
    ("action", "expected_error"),
    [
        ("add", "only members can call"),
        ("approve", "only members can call"),
        ("deposit", "only members can call"),
    ],
)
def test_non_member_cannot_add_approve_or_deposit(localnet_setup, action: str, expected_error: str):
    algorand, creator, member_b, _, outsider = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    if action == "deposit":
        with pytest.raises(Exception, match=expected_error):
            _deposit(
                algorand,
                app_client,
                outsider,
                25_000,
                payment_sender=outsider,
            )
        return

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=25_000, description="Seed expense"),
        params=_app_call_params(creator),
        send_params=_send_params(),
    )

    if action == "add":
        with pytest.raises(Exception, match=expected_error):
            app_client.send.add_expense(
                args=AddExpenseArgs(amount=25_000, description="Invalid caller"),
                params=_app_call_params(outsider),
                send_params=_send_params(),
            )
    else:
        with pytest.raises(Exception, match=expected_error):
            app_client.send.approve_expense(
                args=ApproveExpenseArgs(expense_id=1),
                params=_app_call_params(outsider),
                send_params=_send_params(),
            )


@pytest.mark.parametrize(
    ("payment_sender", "call_sender", "receiver", "amount", "expected_error"),
    [
        ("creator", "member_b", "app", 25_000, "payment sender mismatch|should have been authorized by"),
        ("creator", "creator", "outsider", 25_000, "payment must go to app"),
        ("creator", "creator", "app", 0, "deposit must be positive"),
    ],
)
def test_grouped_deposit_validation(
    localnet_setup,
    payment_sender: str,
    call_sender: str,
    receiver: str,
    amount: int,
    expected_error: str,
):
    algorand, creator, member_b, _, outsider = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    account_lookup = {
        "creator": creator,
        "member_b": member_b,
        "outsider": outsider,
    }
    payment_account = account_lookup[payment_sender]
    sender_account = account_lookup[call_sender]
    receiver_address = app_client.app_address if receiver == "app" else outsider.address

    with pytest.raises(Exception, match=expected_error):
        _deposit(
            algorand,
            app_client,
            sender_account,
            amount,
            payment_sender=payment_account,
            receiver=receiver_address,
        )
def test_cannot_settle_before_threshold(localnet_setup):
    algorand, creator, member_b, _, _ = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    _deposit(algorand, app_client, creator, 200_000)

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=100_000, description="Needs more approvals"),
        params=_app_call_params(creator),
        send_params=_send_params(),
    )

    with pytest.raises(Exception):
        app_client.send.settle_expense(
            args=SettleExpenseArgs(expense_id=1),
            params=_app_call_params(creator),
            send_params=_send_params(),
        )


def test_cannot_double_approve_same_expense(localnet_setup):
    algorand, creator, member_b, _, _ = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=100_000, description="Double approval check"),
        params=_app_call_params(creator),
        send_params=_send_params(),
    )

    app_client.send.approve_expense(
        args=ApproveExpenseArgs(expense_id=1),
        params=_app_call_params(member_b),
        send_params=_send_params(),
    )

    with pytest.raises(Exception):
        app_client.send.approve_expense(
            args=ApproveExpenseArgs(expense_id=1),
            params=_app_call_params(member_b),
            send_params=_send_params(),
        )


def test_cannot_double_settle_same_expense(localnet_setup):
    algorand, creator, member_b, _, _ = localnet_setup

    app_client = _deploy_group(
        algorand=algorand,
        creator=creator,
        members=[creator, member_b],
        threshold=2,
    )

    _deposit(algorand, app_client, creator, 200_000)

    app_client.send.add_expense(
        args=AddExpenseArgs(amount=100_000, description="Double settlement check"),
        params=_app_call_params(member_b),
        send_params=_send_params(),
    )

    app_client.send.approve_expense(
        args=ApproveExpenseArgs(expense_id=1),
        params=_app_call_params(creator),
        send_params=_send_params(),
    )

    app_client.send.settle_expense(
        args=SettleExpenseArgs(expense_id=1),
        params=_settle_params(creator),
        send_params=_send_params(),
    )

    expense_state = app_client.state.box.expenses.get_value(1)
    global_state = app_client.state.global_state

    assert expense_state is not None
    assert global_state is not None
    assert expense_state.settled is True
    assert global_state.pool_balance == 100_000

    with pytest.raises(Exception, match="expense already settled"):
        app_client.send.settle_expense(
            args=SettleExpenseArgs(expense_id=1),
            params=_settle_params(creator),
            send_params=_send_params(),
        )
