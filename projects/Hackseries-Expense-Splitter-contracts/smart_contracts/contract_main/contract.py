from algopy import (
    Account,
    ARC4Contract,
    BoxMap,
    Global,
    GlobalState,
    String,
    Struct,
    Txn,
    UInt64,
    arc4,
    gtxn,
    itxn,
)
from algopy.arc4 import abimethod


class ApprovalKey(Struct):
    expense_id: UInt64
    member: Account


class ExpenseRecord(Struct):
    payer: Account
    amount: UInt64
    description: String
    approval_count: UInt64
    settled: bool


class ExpensePoolContract(ARC4Contract):
    def __init__(self) -> None:
        # Global state
        self.creator = GlobalState(Account)
        self.group_name = GlobalState(String)
        self.member_count = GlobalState(UInt64)
        self.members_initialized = GlobalState(UInt64)
        self.approval_threshold = GlobalState(UInt64)
        self.pool_balance = GlobalState(UInt64)
        self.expense_count = GlobalState(UInt64)

        # Box storage maps
        self.members = BoxMap(Account, UInt64, key_prefix=b"member_")
        self.expenses = BoxMap(UInt64, ExpenseRecord, key_prefix=b"expense_")
        self.approvals = BoxMap(ApprovalKey, UInt64, key_prefix=b"approval_")

    def _assert_group_initialized(self) -> None:
        creator_value, creator_exists = self.creator.maybe()
        assert creator_exists, "group not initialized"

    def _assert_member(self, account: Account) -> None:
        assert self.members_initialized.value == UInt64(1), "members not initialized"
        assert account in self.members, "only members can call"

    @abimethod(create="require")
    def create_group(
        self,
        group_name: String,
        member_addresses: arc4.DynamicArray[arc4.Address],
        approval_threshold: UInt64,
    ) -> None:
        assert member_addresses.length > 0, "members required"

        self.creator.value = Txn.sender
        self.group_name.value = group_name

        unique_members = member_addresses.length

        assert approval_threshold > 0, "threshold must be positive"
        assert approval_threshold <= unique_members, "threshold too high"

        self.member_count.value = unique_members
        self.members_initialized.value = UInt64(0)
        self.approval_threshold.value = approval_threshold
        self.pool_balance.value = UInt64(0)
        self.expense_count.value = UInt64(0)

    @abimethod
    def register_members(self, member_addresses: arc4.DynamicArray[arc4.Address]) -> None:
        self._assert_group_initialized()
        assert Txn.sender == self.creator.value, "only creator can register members"
        assert self.members_initialized.value == UInt64(0), "members already initialized"
        assert member_addresses.length == self.member_count.value, "member count mismatch"

        for member in member_addresses:
            member_account = member.native
            assert member_account not in self.members, "duplicate member"
            self.members[member_account] = UInt64(1)

        self.members_initialized.value = UInt64(1)

    @abimethod
    def deposit_to_pool(self, pay_txn: gtxn.PaymentTransaction) -> None:
        self._assert_group_initialized()
        self._assert_member(Txn.sender)

        assert pay_txn.sender == Txn.sender, "payment sender mismatch"
        assert (
            pay_txn.receiver == Global.current_application_address
        ), "payment must go to app"
        assert pay_txn.amount > 0, "deposit must be positive"
        assert pay_txn.rekey_to == Global.zero_address, "rekey not allowed"
        assert (
            pay_txn.close_remainder_to == Global.zero_address
        ), "close remainder not allowed"

        self.pool_balance.value += pay_txn.amount

    @abimethod
    def add_expense(self, amount: UInt64, description: String) -> None:
        self._assert_group_initialized()
        self._assert_member(Txn.sender)

        assert amount > 0, "amount must be positive"
        assert description.bytes.length > 0, "description required"

        expense_id = self.expense_count.value + UInt64(1)
        self.expense_count.value = expense_id

        self.expenses[expense_id] = ExpenseRecord(
            payer=Txn.sender,
            amount=amount,
            description=description,
            approval_count=UInt64(1),
            settled=False,
        )

        self.approvals[ApprovalKey(expense_id=expense_id, member=Txn.sender)] = UInt64(1)

    @abimethod
    def approve_expense(self, expense_id: UInt64) -> None:
        self._assert_group_initialized()
        self._assert_member(Txn.sender)

        assert expense_id in self.expenses, "expense not found"
        expense = self.expenses[expense_id].copy()
        assert not expense.settled, "expense already settled"

        approval_key = ApprovalKey(expense_id=expense_id, member=Txn.sender)
        approval_result = self.approvals.maybe(approval_key)
        already_approved = approval_result[1]
        assert not already_approved, "already approved"

        self.approvals[approval_key] = UInt64(1)
        expense.approval_count += 1
        self.expenses[expense_id] = expense.copy()

    @abimethod
    def settle_expense(self, expense_id: UInt64) -> None:
        self._assert_group_initialized()
        self._assert_member(Txn.sender)

        assert expense_id in self.expenses, "expense not found"
        expense = self.expenses[expense_id].copy()
        assert not expense.settled, "expense already settled"
        assert (
            expense.approval_count >= self.approval_threshold.value
        ), "insufficient approvals"
        assert self.pool_balance.value >= expense.amount, "insufficient pool balance"

        itxn.Payment(amount=expense.amount, receiver=expense.payer, fee=0).submit()

        self.pool_balance.value -= expense.amount
        expense.settled = True
        self.expenses[expense_id] = expense.copy()

    @abimethod(readonly=True)
    def get_group_info(self) -> tuple[String, UInt64, UInt64, UInt64, UInt64]:
        self._assert_group_initialized()
        return (
            self.group_name.value,
            self.member_count.value,
            self.approval_threshold.value,
            self.pool_balance.value,
            self.expense_count.value,
        )

    @abimethod(readonly=True)
    def get_expense_info(
        self, expense_id: UInt64
    ) -> tuple[arc4.Address, UInt64, String, UInt64, bool]:
        assert expense_id in self.expenses, "expense not found"
        expense = self.expenses[expense_id].copy()
        return (
            arc4.Address(expense.payer),
            expense.amount,
            expense.description,
            expense.approval_count,
            expense.settled,
        )
