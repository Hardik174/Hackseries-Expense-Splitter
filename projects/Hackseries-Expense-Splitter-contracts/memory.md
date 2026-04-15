# Smart Contract Memory

## 1. Project Overview
- Project name: Hackseries-Expense-Splitter-contracts
- Contract system: ExpensePoolContract
- Purpose: Manage a pooled wallet with member-based expense creation, approval, and settlement from app escrow.
- Feature scope: MVP only (single-group flow in one app instance).

## 2. Tech Stack
- AlgoKit
- ARC-4 ABI
- Python smart contracts (Algorand Python / algopy)
- Algorand AVM
- Box Storage
- Global State

## 3. Contract Structure
- Contract name: ExpensePoolContract
- Responsibilities:
  - Initialize one member group with approval threshold.
  - Accept grouped member deposits into app escrow.
  - Store expenses in box storage with lifecycle status.
  - Track per-expense approvals and prevent duplicate approvals.
  - Settle approved expenses via inner payment from app escrow.
  - Expose read methods for group and expense details.

### Escrow Model
- The application account acts as the escrow wallet.
- All deposits are made to the app address via grouped transactions.
- Funds are stored in the app account balance.
- Settlements are executed using inner transactions from the app account to the expense payer.

## 4. Global State Schema
- `creator`
  - Type: Account
  - Purpose: Group creator and initialization marker.
- `group_name`
  - Type: String
  - Purpose: Human-readable group identifier.
- `member_count`
  - Type: UInt64
  - Purpose: Number of unique group members.
- `approval_threshold`
  - Type: UInt64
  - Purpose: Minimum approvals required to settle an expense.
- `pool_balance`
  - Type: UInt64
  - Purpose: Internal accounting of deposited ALGO available for settlement.
- `expense_count`
  - Type: UInt64
  - Purpose: Monotonic counter used to assign expense IDs.

## 5. Box Storage Schema
### Members
- Key format: `member_` + address
- Value format: UInt64 (`1` indicates membership)
- Backing map: `BoxMap(Account, UInt64, key_prefix=b"member_")`

### Expenses
- Key format: `expense_` + expense_id
- Value format: `ExpenseRecord` struct
  - `payer`: Account
  - `amount`: UInt64
  - `description`: String
  - `approval_count`: UInt64
  - `settled`: bool
- `expense_id` is generated using a monotonic global counter (`expense_count`).
- This guarantees uniqueness within the contract instance.
- Backing map: `BoxMap(UInt64, ExpenseRecord, key_prefix=b"expense_")`

### Approvals
- Key format: `approval_` + (expense_id, address)
- Value format: UInt64 (`1` indicates approved)
- Purpose: Track if a member has approved a specific expense.
- Backing map: `BoxMap(ApprovalKey, UInt64, key_prefix=b"approval_")`

## 6. Methods Implemented
### create_group
- Inputs:
  - `group_name: String`
  - `member_addresses: arc4.DynamicArray[arc4.Address]`
  - `approval_threshold: UInt64`
- Logic summary:
  - Requires create call.
  - Stores creator and group metadata.
  - Inserts unique members into member boxes.
  - Validates threshold > 0 and <= unique member count.
  - Initializes `pool_balance` and `expense_count` to 0.
- State changes:
  - Updates all global fields.
  - Creates member boxes.

### deposit_to_pool
- Inputs:
  - `pay_txn: gtxn.PaymentTransaction`
- Logic summary:
  - Requires initialized group and sender membership.
  - Verifies grouped payment sender, receiver, amount, and safety fields.
  - Adds payment amount to `pool_balance`.
- State changes:
  - Increments `pool_balance`.

### add_expense
- Inputs:
  - `amount: UInt64`
  - `description: String`
- Logic summary:
  - Requires initialized group and sender membership.
  - Validates non-zero amount and non-empty description.
  - Increments expense counter and creates expense record.
  - The payer automatically approves their own expense at creation.
  - `approval_count` starts at 1.
  - Creates the payer approval entry in the approvals map.
- State changes:
  - Increments `expense_count`.
  - Creates/updates one expense box.
  - Creates one approval box.

### approve_expense
- Inputs:
  - `expense_id: UInt64`
- Logic summary:
  - Requires initialized group and sender membership.
  - Ensures expense exists and is not settled.
  - Ensures sender has not already approved.
  - Records approval and increments approval count.
- State changes:
  - Creates one approval box.
  - Updates expense record approval count.

### settle_expense
- Inputs:
  - `expense_id: UInt64`
- Logic summary:
  - Requires initialized group and sender membership.
  - Ensures expense exists, is not settled, and has enough approvals.
  - Ensures pool balance covers expense amount.
  - Sends inner payment from app escrow to payer.
  - Marks expense settled and decrements pool balance.
- State changes:
  - Inner transaction (payment from app escrow).
  - Decrements `pool_balance`.
  - Updates expense record `settled = true`.

### get_group_info
- Inputs: none
- Logic summary:
  - Requires initialized group.
  - Returns group metadata and counters.
- State changes: none (readonly)

### get_expense_info
- Inputs:
  - `expense_id: UInt64`
- Logic summary:
  - Validates expense existence.
  - Returns payer, amount, description, approvals, and settlement status.
- State changes: none (readonly)

## 7. Method Classification
### State-changing methods
- `create_group`
- `deposit_to_pool`
- `add_expense`
- `approve_expense`
- `settle_expense`

### Read-only methods
- `get_group_info`
- `get_expense_info`

## 8. Transaction Flow
- Step 1: Group creation
  - Creator calls `create_group(...)` at app creation time.
  - Contract writes creator/group metadata, inserts members, and initializes counters.
- Step 2: Deposit flow (grouped transaction)
  - Caller prepares a payment transaction to the app address.
  - Caller submits `deposit_to_pool(pay_txn)` in the same atomic group.
  - Contract validates grouped payment fields (sender match, app receiver, positive amount, rekey/close protections).
  - Contract increments `pool_balance`.
- Step 3: Expense creation
  - Member calls `add_expense(amount, description)`.
  - Contract assigns a new expense ID from monotonic `expense_count`.
  - Contract stores the expense and auto-approves payer (`approval_count = 1`).
- Step 4: Approval flow
  - Member calls `approve_expense(expense_id)`.
  - Contract rejects duplicate approvals using approval key `(expense_id, member)`.
  - Contract increments expense `approval_count`.
- Step 5: Settlement flow
  - Member calls `settle_expense(expense_id)`.
  - Contract enforces approval threshold (`approval_count >= approval_threshold`) and sufficient `pool_balance`.
  - Contract pays the expense payer via inner payment from the app account.
  - Contract marks expense as settled and decrements `pool_balance`.

## 9. Security Considerations
- Group initialization definition:
  - Group is considered initialized when `creator` is set (non-zero address / exists in global state).
  - All methods except `create_group` require initialized state.
- Membership checks:
  - Enforced before deposit, add, approve, and settle.
- Double approval prevention:
  - Approval key is expense + member and checked before insert.
- Settlement checks:
  - Must exist, must be unsettled, must meet threshold, must have sufficient pool balance.
- Transaction safety checks on deposit:
  - Receiver must be app address.
  - Sender must match caller.
  - Positive amount required.
  - Rekey/close fields disallowed.

## 10. Transaction Cost Model
- Users pay transaction fees for all app calls.
- Deposit requires a grouped payment + app call transaction.
- Inner transactions (settlement) are covered by the outer transaction fee budget.

## 11. Assumptions
- Single group per contract app instance.
- No dispute/arbitration system.
- No NFT integration.
- No UPI integration.
- No multi-group logic.
- No per-user balance accounting beyond pooled funds and approvals.

## 12. Change Log
- [2026-04-15] Created ExpensePoolContract with ARC-4 ABI methods for create group, deposit, add expense, approve expense, settle expense, and read-only info queries.
- [2026-04-15] Implemented global state + box storage schema for members, expenses, and approvals.
- [2026-04-15] Added security checks for membership, duplicate approvals, settlement gating, and grouped deposit validation.
- [2026-04-15] Added deployment wiring for method-based app creation using `create_group` in `deploy_config.py`.
- [2026-04-15] Established this `memory.md` as canonical smart contract system memory file; future code/storage/logic changes must append update entries here.
- [2026-04-15] Refined documentation to include escrow model, approval logic clarification, expense ID guarantees, initialization definition, method classification, and transaction cost model.
- [2026-04-15] Added AlgoKit integration test coverage for create, deposit, add, approve, and settle flows with success and failure scenarios.
- [2026-04-15] Added `pytest` as a dev dependency to execute integration tests in the contracts project.
- [2026-04-15] Updated integration test setup to skip gracefully when LocalNet is not running.
- [2026-04-15] Added full integration test coverage (success + failure cases), improved test robustness, validated contract-client interaction, and added testing + demo documentation sections.

## 13. Testing
- Integration tests are implemented with AlgoKit and LocalNet.
- The test suite covers the full success flow: create → deposit → add → approve → settle.
- The test suite covers failure cases: non-member access, insufficient approvals, duplicate approvals, double settlement, and grouped deposit validation.
- The test suite skips gracefully with a clear message when LocalNet is not running.

## 14. How to Run Tests
1. Start LocalNet:
   algokit localnet start
2. Run tests:
   poetry run pytest
3. Expected:
   - Success scenarios pass.
   - Failure scenarios raise expected exceptions.
   - Tests skip cleanly if LocalNet is unavailable.

## 15. Demo Flow
1. Create group
2. Deposit funds into pool
3. Add expense
4. Approve expense
5. Settle expense

Demonstrates:
- Escrow-based pooled wallet

## 16. Stable Local Runbook (Repeatable)
Use this exact sequence for local development, deployment, and smoke checks.

### Prerequisites
- AlgoKit CLI installed and on PATH.
- Poetry installed and usable from terminal.
- Node.js + npm installed for frontend.

### A. Start LocalNet
From workspace root:

```powershell
Set-Location "c:\Users\Hardik Rokde\Hackseries\Hackseries-Expense-Splitter"
algokit localnet start
```

### B. Deploy Contracts (with printed app details)
From contracts project:

```powershell
Set-Location "c:\Users\Hardik Rokde\Hackseries\Hackseries-Expense-Splitter\projects\Hackseries-Expense-Splitter-contracts"
algokit project deploy
```

Expected deployment log now includes:
- App name
- App ID
- App address
- Deployer address
- Network
- Deployment operation result
- Group info
- Frontend URL
- App explorer link
- App account link

### C. Contract Smoke Tests
From contracts project:

```powershell
poetry run pytest -q
```

Expected: full pass on LocalNet.

### D. Frontend Build Smoke
From frontend project:

```powershell
Set-Location "c:\Users\Hardik Rokde\Hackseries\Hackseries-Expense-Splitter\projects\Hackseries-Expense-Splitter-frontend"
npm run build
```

Expected: Vite build success.

### E. Run Frontend and Try App
From frontend project:

```powershell
npm run dev
```

Open:
- http://localhost:5173/

In UI:
1. Connect wallet.
2. Open Expense Pool Contract Demo.
3. Confirm App ID is set to deployed app (default from `.env`).
4. Run: Refresh Group Info, Deposit, Add Expense, Approve Expense, Settle Expense.

### F. Current Verified Local Deployment Snapshot
- App name: ExpensePoolContract
- App ID: 1003
- App address: FPKJ7KD37AEIB3MJ6WXEXJIZH4DACLBNCR5PNUQREUWMC2YLIWFH2NHX24
- Network: localnet
- Frontend URL: http://localhost:5173/
- App explorer: https://lora.algokit.io/localnet/application/1003
- App account explorer: https://lora.algokit.io/localnet/account/FPKJ7KD37AEIB3MJ6WXEXJIZH4DACLBNCR5PNUQREUWMC2YLIWFH2NHX24

### G. Current Verified TestNet Deployment Snapshot
- App name: ExpensePoolContract
- App ID: 758861618
- App address: 24EFC2B3EQ3SI3TJSLN7JHIC3AQDAW2PM4B4Q7LQCKYIEY5FDCRR53RNS4
- Deployer address: Q6AWGH4CQ2C5YKVTD7TZWFXB4INOMBG2TT7MQ3XXP5NPCBZNPLWF3YJDCU
- Network: testnet
- Frontend URL: http://localhost:5173/
- App explorer: https://lora.algokit.io/testnet/application/758861618
- App account explorer: https://lora.algokit.io/testnet/account/24EFC2B3EQ3SI3TJSLN7JHIC3AQDAW2PM4B4Q7LQCKYIEY5FDCRR53RNS4
- Frontend testnet profile: [projects/Hackseries-Expense-Splitter-frontend/.env.testnet](../Hackseries-Expense-Splitter-frontend/.env.testnet)

### H. TestNet Next Step
- Use the frontend testnet profile for hosted deployment or local testnet validation.
- Keep the contracts `.env` file temporary when supplying secrets for deployment, then remove it after deploy.

### G. Stop Frontend Server
Press `Ctrl+C` in the terminal running `npm run dev`.
- Approval-based governance
- Trustless settlement
