// src/components/Home.tsx
import { useWallet } from '@txnlab/use-wallet-react'
import React, { useState } from 'react'
import ConnectWallet from './components/ConnectWallet'
import Transact from './components/Transact'
import AppCalls from './components/AppCalls'

interface HomeProps {}

const Home: React.FC<HomeProps> = () => {
  const [openWalletModal, setOpenWalletModal] = useState<boolean>(false)
  const [openDemoModal, setOpenDemoModal] = useState<boolean>(false)
  const [appCallsDemoModal, setAppCallsDemoModal] = useState<boolean>(false)
  const { activeAddress } = useWallet()

  const toggleWalletModal = () => {
    setOpenWalletModal(!openWalletModal)
  }

  const toggleDemoModal = () => {
    setOpenDemoModal(!openDemoModal)
  }

  const toggleAppCallsModal = () => {
    setAppCallsDemoModal(!appCallsDemoModal)
  }

  return (
    <div className="hero">
      <div className="hero-content">
        <div>
          <h1 className="text-4xl font-bold">
            Hackseries
          </h1>
          <h2 className="text-2xl font-bold text-teal-600">
            Expense Splitter
          </h2>
          <p className="text-sm py-4 text-gray-600">
            Connect wallet & interact with the Expense Pool contract
          </p>

          <button data-test-id="connect-wallet" className="btn btn-primary w-full" onClick={toggleWalletModal}>
            {activeAddress ? '✓ Wallet Connected' : 'Connect Wallet'}
          </button>

          {activeAddress && (
            <>
              <button data-test-id="transactions-demo" className="btn w-full" onClick={toggleDemoModal}>
                Send ALGO Demo
              </button>

              <button data-test-id="appcalls-demo" className="btn btn-primary w-full" onClick={toggleAppCallsModal}>
                Contract Demo
              </button>
            </>
          )}
        </div>
      </div>

      <ConnectWallet openModal={openWalletModal} closeModal={toggleWalletModal} />
      <Transact openModal={openDemoModal} setModalState={setOpenDemoModal} />
      <AppCalls openModal={appCallsDemoModal} setModalState={setAppCallsDemoModal} />
    </div>
  )
}

export default Home
