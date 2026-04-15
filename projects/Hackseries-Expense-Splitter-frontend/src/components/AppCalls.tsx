import { algo, AlgorandClient } from '@algorandfoundation/algokit-utils'
import { useWallet } from '@txnlab/use-wallet-react'
import { useSnackbar } from 'notistack'
import { useMemo, useState } from 'react'
import { ExpensePoolContractClient } from '../contracts/ExpensePoolContract'
import { getAlgodConfigFromViteEnvironment, getIndexerConfigFromViteEnvironment } from '../utils/network/getAlgoClientConfigs'

interface AppCallsInterface {
  openModal: boolean
  setModalState: (value: boolean) => void
}

const AppCalls = ({ openModal, setModalState }: AppCallsInterface) => {
  const [loading, setLoading] = useState<boolean>(false)
  const [appIdInput, setAppIdInput] = useState<string>(import.meta.env.VITE_EXPENSE_POOL_APP_ID ?? '')
  const [depositAmount, setDepositAmount] = useState<string>('1')
  const [expenseAmount, setExpenseAmount] = useState<string>('0.2')
  const [expenseDescription, setExpenseDescription] = useState<string>('Dinner split')
  const [expenseIdInput, setExpenseIdInput] = useState<string>('1')
  const [groupInfo, setGroupInfo] = useState<string>('No group info loaded yet.')
  const [expenseInfo, setExpenseInfo] = useState<string>('No expense info loaded yet.')

  const { enqueueSnackbar } = useSnackbar()
  const { transactionSigner, activeAddress } = useWallet()

  const algodConfig = getAlgodConfigFromViteEnvironment()
  const indexerConfig = getIndexerConfigFromViteEnvironment()
  const algorand = useMemo(
    () =>
      AlgorandClient.fromConfig({
        algodConfig,
        indexerConfig,
      }),
    [algodConfig, indexerConfig],
  )

  if (activeAddress && transactionSigner) {
    algorand.setSigner(activeAddress, transactionSigner)
  }

  const appId = appIdInput ? BigInt(appIdInput) : undefined
  const appClient = appId
    ? new ExpensePoolContractClient({
        algorand,
        appId,
        defaultSender: activeAddress ?? undefined,
      })
    : undefined

  const withLoader = async (action: () => Promise<void>) => {
    setLoading(true)
    try {
      await action()
    } finally {
      setLoading(false)
    }
  }

  const assertReady = () => {
    if (!activeAddress || !transactionSigner) {
      enqueueSnackbar('Please connect your wallet first.', { variant: 'warning' })
      return false
    }
    if (!appClient) {
      enqueueSnackbar('Set a valid App ID first.', { variant: 'warning' })
      return false
    }
    return true
  }

  const loadGroupInfo = async () => {
    await withLoader(async () => {
      if (!appClient) {
        enqueueSnackbar('Set a valid App ID first.', { variant: 'warning' })
        return
      }

      const result = await appClient.send.getGroupInfo({ args: [] })
      if (!result.return) {
        enqueueSnackbar('No response received from group info call.', { variant: 'warning' })
        return
      }

      const [name, memberCount, threshold, poolBalance, expenseCount] = result.return
      setGroupInfo(
        `Group: ${name} | Members: ${memberCount.toString()} | Threshold: ${threshold.toString()} | Pool: ${poolBalance.toString()} uALGO | Expenses: ${expenseCount.toString()}`,
      )
      enqueueSnackbar('Group info loaded.', { variant: 'success' })
    })
  }

  const loadExpenseInfo = async () => {
    await withLoader(async () => {
      if (!appClient) {
        enqueueSnackbar('Set a valid App ID first.', { variant: 'warning' })
        return
      }

      const expenseId = BigInt(expenseIdInput || '0')
      const result = await appClient.send.getExpenseInfo({ args: { expenseId } })
      if (!result.return) {
        enqueueSnackbar('No response received from expense info call.', { variant: 'warning' })
        return
      }

      const [payer, amount, description, approvalCount, settled] = result.return
      setExpenseInfo(
        `Expense ${expenseId.toString()}: payer=${payer}, amount=${amount.toString()} uALGO, approvals=${approvalCount.toString()}, settled=${String(settled)}, description="${description}"`,
      )
      enqueueSnackbar('Expense info loaded.', { variant: 'success' })
    })
  }

  const depositToPool = async () => {
    await withLoader(async () => {
      if (!assertReady() || !appClient || !activeAddress) {
        return
      }

      const amount = Number(depositAmount)
      if (!Number.isFinite(amount) || amount <= 0) {
        enqueueSnackbar('Deposit amount must be a positive number.', { variant: 'warning' })
        return
      }

      const payTxn = await algorand.createTransaction.payment({
        sender: activeAddress,
        receiver: appClient.appAddress,
        amount: algo(amount),
      })

      await appClient.send.depositToPool({ args: { payTxn } })
      enqueueSnackbar('Deposit submitted successfully.', { variant: 'success' })
      await loadGroupInfo()
    })
  }

  const addExpense = async () => {
    await withLoader(async () => {
      if (!assertReady() || !appClient) {
        return
      }

      const amount = Number(expenseAmount)
      if (!Number.isFinite(amount) || amount <= 0) {
        enqueueSnackbar('Expense amount must be a positive number.', { variant: 'warning' })
        return
      }
      if (!expenseDescription.trim()) {
        enqueueSnackbar('Expense description is required.', { variant: 'warning' })
        return
      }

      await appClient.send.addExpense({
        args: {
          amount: algo(amount).microAlgos,
          description: expenseDescription.trim(),
        },
      })
      enqueueSnackbar('Expense added.', { variant: 'success' })
      await loadGroupInfo()
    })
  }

  const approveExpense = async () => {
    await withLoader(async () => {
      if (!assertReady() || !appClient) {
        return
      }

      const expenseId = BigInt(expenseIdInput || '0')
      await appClient.send.approveExpense({ args: { expenseId } })
      enqueueSnackbar('Expense approved.', { variant: 'success' })
      await loadExpenseInfo()
    })
  }

  const settleExpense = async () => {
    await withLoader(async () => {
      if (!assertReady() || !appClient) {
        return
      }

      const expenseId = BigInt(expenseIdInput || '0')
      await appClient.send.settleExpense({
        args: { expenseId },
        extraFee: algo(0.001),
      })
      enqueueSnackbar('Expense settled.', { variant: 'success' })
      await loadGroupInfo()
      await loadExpenseInfo()
    })
  }

  return (
    <dialog id="appcalls_modal" className={`modal ${openModal ? 'modal-open' : ''} bg-slate-200`} style={{ display: openModal ? 'block' : 'none' }}>
      <form method="dialog" className="modal-box app-calls-box">
        <h3 className="font-bold text-lg">Expense Pool Demo</h3>
        <p className="helper-text">Connect wallet, set your deployed App ID, then interact with the contract.</p>

        <div className="field-row">
          <label className="field-label" htmlFor="app-id-input">
            App ID
          </label>
          <input
            id="app-id-input"
            type="number"
            min="1"
            placeholder="e.g. 1003"
            className="input input-bordered w-full"
            value={appIdInput}
            onChange={(e) => setAppIdInput(e.target.value)}
          />
        </div>

        <div className="button-grid">
          <button type="button" className="btn" onClick={loadGroupInfo}>
            Refresh Group Info
          </button>
          <button type="button" className="btn" onClick={loadExpenseInfo}>
            Fetch Expense By ID
          </button>
        </div>

        <div className="field-row">
          <label className="field-label" htmlFor="expense-id-input">
            Expense ID
          </label>
          <input
            id="expense-id-input"
            type="number"
            min="1"
            className="input input-bordered w-full"
            value={expenseIdInput}
            onChange={(e) => setExpenseIdInput(e.target.value)}
          />
        </div>

        <div className="field-row">
          <label className="field-label" htmlFor="deposit-input">
            Deposit (ALGO)
          </label>
          <input
            id="deposit-input"
            type="number"
            min="0"
            step="0.001"
            className="input input-bordered w-full"
            value={depositAmount}
            onChange={(e) => setDepositAmount(e.target.value)}
          />
          <button type="button" className="btn" onClick={depositToPool}>
            Deposit To Pool
          </button>
        </div>

        <div className="field-row">
          <label className="field-label" htmlFor="expense-amount-input">
            Expense Amount (ALGO)
          </label>
          <input
            id="expense-amount-input"
            type="number"
            min="0"
            step="0.001"
            className="input input-bordered w-full"
            value={expenseAmount}
            onChange={(e) => setExpenseAmount(e.target.value)}
          />
        </div>

        <div className="field-row">
          <label className="field-label" htmlFor="expense-description-input">
            Expense Description
          </label>
          <input
            id="expense-description-input"
            type="text"
            className="input input-bordered w-full"
            value={expenseDescription}
            onChange={(e) => setExpenseDescription(e.target.value)}
          />
        </div>

        <div className="button-grid">
          <button type="button" className="btn" onClick={addExpense}>
            Add Expense
          </button>
          <button type="button" className="btn" onClick={approveExpense}>
            Approve Expense
          </button>
          <button type="button" className="btn btn-warning" onClick={settleExpense}>
            Settle Expense
          </button>
        </div>

        <div className="info-panel">{groupInfo}</div>
        <div className="info-panel">{expenseInfo}</div>

        <div className="modal-action ">
          <button type="button" className="btn" onClick={() => setModalState(!openModal)}>
            Close
          </button>
          <button type="button" className="btn" onClick={loadGroupInfo}>
            {loading ? <span className="loading loading-spinner" /> : 'Run Demo Action'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

export default AppCalls
