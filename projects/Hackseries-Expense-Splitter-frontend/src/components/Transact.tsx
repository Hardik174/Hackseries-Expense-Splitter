import { algo, AlgorandClient } from '@algorandfoundation/algokit-utils'
import { useWallet } from '@txnlab/use-wallet-react'
import { useSnackbar } from 'notistack'
import { useMemo, useState } from 'react'
import { getAlgodConfigFromViteEnvironment } from '../utils/network/getAlgoClientConfigs'

interface TransactInterface {
  openModal: boolean
  setModalState: (value: boolean) => void
}

const Transact = ({ openModal, setModalState }: TransactInterface) => {
  const [loading, setLoading] = useState<boolean>(false)
  const [receiverAddress, setReceiverAddress] = useState<string>('')
  const [amountAlgo, setAmountAlgo] = useState<string>('1')

  const algodConfig = getAlgodConfigFromViteEnvironment()
  const algorand = AlgorandClient.fromConfig({ algodConfig })
  const networkName = useMemo(() => {
    return algodConfig.network === '' ? 'localnet' : algodConfig.network.toLocaleLowerCase()
  }, [algodConfig.network])

  const { enqueueSnackbar } = useSnackbar()

  const { transactionSigner, activeAddress } = useWallet()

  const handleSubmitAlgo = async () => {
    setLoading(true)
    try {
      if (!transactionSigner || !activeAddress) {
        enqueueSnackbar('Please connect wallet first', { variant: 'warning' })
        return
      }

      const parsedAmount = Number(amountAlgo)
      if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
        enqueueSnackbar('Please enter a valid amount greater than 0.', { variant: 'warning' })
        return
      }

      // Pre-check available spendable balance so failed sends are caught before signing.
      const accountInfo = await algorand.client.algod.accountInformation(activeAddress).do()
      const spendableMicroAlgos = Math.max(0, Number(accountInfo.amount) - Number(accountInfo.minBalance))
      const requiredMicroAlgos = Math.round(parsedAmount * 1_000_000) + 1_000

      if (spendableMicroAlgos < requiredMicroAlgos) {
        enqueueSnackbar(
          `Insufficient funds on ${networkName}. Spendable: ${(spendableMicroAlgos / 1_000_000).toFixed(6)} ALGO; required (amount + fee): ${(requiredMicroAlgos / 1_000_000).toFixed(6)} ALGO.`,
          { variant: 'error' },
        )
        return
      }

      enqueueSnackbar('Sending transaction...', { variant: 'info' })
      const result = await algorand.send.payment({
        signer: transactionSigner,
        sender: activeAddress,
        receiver: receiverAddress,
        amount: algo(parsedAmount),
      })

      const txId = result.txIds[0]
      enqueueSnackbar(`Transaction confirmed on ${networkName}: ${txId}`, { variant: 'success' })
      enqueueSnackbar(`Explorer: https://lora.algokit.io/${networkName}/transaction/${txId}`, { variant: 'info' })
      setReceiverAddress('')
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unknown error'
      enqueueSnackbar(`Failed to send transaction: ${message}`, { variant: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <dialog id="transact_modal" className={`modal ${openModal ? 'modal-open' : ''} bg-slate-200`}style={{ display: openModal ? 'block' : 'none' }}>
      <form method="dialog" className="modal-box">
        <h3 className="font-bold text-lg">Send payment transaction</h3>
        <p className="helper-text">Active network: {networkName}</p>
        <p className="helper-text">Addresses are valid on every Algorand network. If you are on localnet, the transfer will only appear on localnet explorer, not testnet explorer.</p>
        <br />
        <input
          type="text"
          data-test-id="receiver-address"
          placeholder="Provide wallet address"
          className="input input-bordered w-full"
          value={receiverAddress}
          onChange={(e) => {
            setReceiverAddress(e.target.value)
          }}
        />
        <br />
        <input
          type="number"
          min="0"
          step="0.001"
          data-test-id="amount-algo"
          placeholder="ALGO amount"
          className="input input-bordered w-full"
          value={amountAlgo}
          onChange={(e) => {
            setAmountAlgo(e.target.value)
          }}
        />
        <div className="modal-action grid">
          <button type="button" className="btn" onClick={() => setModalState(!openModal)}>
            Close
          </button>
          <button
            type="button"
            data-test-id="send-algo"
            className={`btn ${receiverAddress.length === 58 && Number(amountAlgo) > 0 ? '' : 'btn-disabled'} lo`}
            onClick={handleSubmitAlgo}
          >
            {loading ? <span className="loading loading-spinner" /> : 'Send ALGO'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

export default Transact
