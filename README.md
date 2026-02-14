# 🤖💰 Agent Economy Demo: Pay, Remember, Act

> **Wallet gives agents capital. TiDB Cloud Zero gives agents memory.**

A working demo showing how AI agents participate in the emerging **Agent Economy** — autonomously paying for data, storing decisions, and taking action.

## The Narrative

AI agents are evolving from "can advise" to **"can pay, can execute, can remember."**

| Layer | What it does | Provider |
|-------|-------------|----------|
| 💰 **Capital** | Agent pays for data/services | Coinbase Agentic Wallets / x402 |
| 🧠 **Memory** | Agent stores state, logs, strategies | TiDB Cloud Zero |
| ⚡ **Action** | Agent executes decisions | Agent framework |

This demo connects all three layers in a real workflow.

## Demo Flow

```
┌─────────────────────────────────────────────────┐
│  1. Agent receives task                         │
│     "Monitor ETH price and alert on volatility" │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  2. Agent requests market data                  │
│     GET /api/v3/coins/ethereum                  │
│     → 402 Payment Required (x402)               │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  3. Agent pays with USDC ($0.01/request)        │
│     x402 protocol: HTTP 402 → auto-pay → data   │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  4. Agent writes to TiDB Cloud Zero             │
│     • Raw market data                           │
│     • Payment audit log                         │
│     • Strategy state & decisions                │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  5. Agent outputs action                        │
│     • Price alerts                              │
│     • Strategy recommendations                  │
│     • Historical analysis from memory           │
└─────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full demo (simulation mode — no wallet needed)
python demo.py

# Run with real x402 payments (requires EVM private key)
pip install eth-account
python demo.py --private-key 0xYOUR_PRIVATE_KEY

# Run with an existing TiDB Cloud Zero connection
python demo.py --connection-string "mysql://user:pass@host:4000/"
```

## x402 Integration Modes

| Mode | What happens | Requirements |
|------|-------------|-------------|
| **Simulation** (default) | Full protocol flow with simulated signing & data | None |
| **Live** | Real EIP-712 signing, real x402 endpoints | `eth-account` + private key |

The x402 client implements the real protocol:
1. `GET /endpoint` → `402 Payment Required` + `PAYMENT-REQUIRED` header
2. Client signs EIP-712 typed data with EVM wallet
3. Resend with `PAYMENT-SIGNATURE` header → data returned
4. Settlement via Coinbase facilitator (`x402.org/facilitator`)

Compatible with any x402-enabled endpoint (CoinGecko, custom APIs, etc.)

## What's Inside

| File | Description |
|------|-------------|
| `demo.py` | Main demo — full agent economy workflow |
| `x402_client.py` | x402 payment protocol client (simulated) |
| `agent_memory.py` | TiDB Cloud Zero memory layer |
| `market_agent.py` | Market monitoring agent with pay-per-use data |

## Architecture

```
Agent Economy Stack
├── Payment Layer (x402 / Coinbase Agentic Wallets)
│   ├── Pay-per-use data access ($0.01 USDC/request)
│   ├── Gasless trading on Base
│   └── Multi-chain support (EVM + Solana)
├── Memory Layer (TiDB Cloud Zero)
│   ├── Market data history
│   ├── Payment audit trail
│   ├── Strategy state machine
│   └── Cross-agent collaboration state
└── Action Layer (Agent Framework)
    ├── Price alerts & monitoring
    ├── Strategy recommendations
    └── [Future] On-chain execution
```

## Why TiDB Cloud Zero?

When agents have wallets, **off-chain data and state management become essential infrastructure.**

- 🔐 **Audit trail** — Every payment and decision logged in SQL
- 🧠 **Agent memory** — Persists across sessions, queryable with SQL
- ⚡ **Instant provisioning** — No signup, no config, database in 2 seconds
- 🤝 **Multi-agent collaboration** — Shared state via distributed SQL
- 🔍 **Vector search** — Semantic memory retrieval built-in

## References

- [Coinbase Agentic Wallets](https://www.coinbase.com/developer-platform/discover/launches/agentic-wallets) — Agent wallet skills
- [x402 Protocol](https://www.x402.org/) — HTTP 402 machine payments
- [Stripe Machine Payments](https://stripe.com) — Pay-per-use USDC
- [CoinGecko](https://www.coingecko.com/) — Market data API
- [TiDB Cloud Zero](https://zero.tidbcloud.com) — Instant databases for agents

## License

MIT

---

🚀 **Get Started with TiDB Cloud:**
* Explore how TiDB works in real workloads — [Try TiDB Cloud](https://tidbcloud.com/free-trial/?utm_source=sales_bdm&utm_medium=sales&utm_content=Siddon) freely.
* Ready to speedup your business on TiDB Cloud — Visit [TiDB Cloud Essential 101](https://www.pingcap.com/essential101/?utm_source=sales_bdm&utm_medium=sales&utm_content=Siddon)
* Want to launch a startup — See [TiDB Cloud Startup Program](https://www.pingcap.com/tidb-cloud-startup-program/?utm_source=sales_bdm&utm_medium=sales&utm_content=Siddon)
* Curious how to build AI apps — Discover [TiDB Cloud AI](https://www.pingcap.com/ai?utm_source=sales_bdm&utm_medium=sales&utm_content=Siddon)
