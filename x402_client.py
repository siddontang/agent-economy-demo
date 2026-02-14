"""
x402 Payment Protocol Client
==============================
Real x402 integration using the official Coinbase x402 Python SDK.

Supports two modes:
1. REAL mode: Uses actual x402 protocol with EVM wallet signing
   - Requires a private key with USDC balance on Base Sepolia (testnet)
   - Connects to real x402-enabled endpoints
2. SIMULATION mode: No wallet needed, simulates the full flow
   - Perfect for demos and development

x402 flow:
  GET /resource → 402 + PAYMENT-REQUIRED header
  → Client signs payment with wallet
  → GET /resource + PAYMENT-SIGNATURE header
  → 200 + data

References:
- x402 Protocol: https://x402.org
- Coinbase x402 SDK: https://github.com/coinbase/x402
- Facilitator: https://x402.org/facilitator
"""

import os
import json
import time
import random
import base64
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

import requests


# ─── Payment Receipt ──────────────────────────────────────────────────

@dataclass
class PaymentReceipt:
    """Receipt for an x402 micro-payment."""
    tx_id: str
    amount_usdc: float
    payer: str
    payee: str
    network: str
    endpoint: str
    timestamp: str
    status: str = "confirmed"
    gas_fee: float = 0.0
    x402_version: int = 2
    scheme: str = "exact"
    settlement_tx: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class X402Response:
    """Response after x402 payment flow."""
    status_code: int
    data: dict
    payment: Optional[PaymentReceipt] = None
    paid: bool = False
    mode: str = "simulation"


# ─── Real x402 Client ────────────────────────────────────────────────

class RealX402Client:
    """
    Real x402 client using the official Coinbase x402 Python SDK.

    Uses EVM wallet (eth-account) to sign payments and the x402.org
    facilitator for settlement on Base Sepolia (testnet).

    Requirements:
    - Private key (set PRIVATE_KEY env var or pass to constructor)
    - USDC balance on Base Sepolia for testnet
    - x402 SDK: pip install "x402[requests,evm]"
    """

    FACILITATOR_URL = "https://x402.org/facilitator"
    # Base Sepolia testnet
    DEFAULT_NETWORK = "eip155:84532"

    def __init__(self, private_key: str = None, network: str = None):
        from eth_account import Account

        self.private_key = private_key or os.environ.get("PRIVATE_KEY")
        if not self.private_key:
            raise ValueError(
                "Private key required for real x402 mode. "
                "Set PRIVATE_KEY env var or pass to constructor."
            )

        self.account = Account.from_key(self.private_key)
        self.wallet_address = self.account.address
        self.network = network or self.DEFAULT_NETWORK

        # Initialize x402 client
        from x402 import x402ClientSync, SchemeRegistration
        from x402.mechanisms.evm.exact import ExactEvmScheme

        self.x402_client = x402ClientSync()
        self.x402_client.register(
            "eip155:*",
            ExactEvmScheme(signer=self.account)
        )

        self.total_spent = 0.0
        self.payment_count = 0
        self.payments: list[PaymentReceipt] = []

    def request(self, url: str, method: str = "GET") -> X402Response:
        """
        Make a request to an x402-enabled endpoint.

        Full flow:
        1. GET url → 402 Payment Required + PAYMENT-REQUIRED header
        2. Parse payment requirements
        3. Sign payment with EVM wallet
        4. Resend with PAYMENT-SIGNATURE header
        5. Receive data
        """
        from x402 import parse_payment_required

        # Step 1: Initial request
        resp = requests.request(method, url)

        if resp.status_code != 402:
            # Not a paid endpoint, return directly
            return X402Response(
                status_code=resp.status_code,
                data=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text},
                paid=False,
                mode="real",
            )

        # Step 2: Parse 402 response
        payment_required_header = resp.headers.get("PAYMENT-REQUIRED")
        if not payment_required_header:
            return X402Response(
                status_code=402,
                data={"error": "No PAYMENT-REQUIRED header in 402 response"},
                paid=False,
                mode="real",
            )

        payment_required = parse_payment_required(payment_required_header)

        # Step 3: Create payment payload (signs with wallet)
        payment_payload = self.x402_client.create_payment_payload(payment_required)

        # Step 4: Serialize and resend
        payload_json = payment_payload.model_dump()
        payload_b64 = base64.b64encode(
            json.dumps(payload_json).encode()
        ).decode()

        headers = {"PAYMENT-SIGNATURE": payload_b64}
        resp2 = requests.request(method, url, headers=headers)

        # Step 5: Process response
        if resp2.status_code == 200:
            # Parse settlement response
            settlement_header = resp2.headers.get("PAYMENT-RESPONSE", "")

            # Extract amount from payment requirements
            amount = 0.01  # default
            try:
                if hasattr(payment_required, 'payment_requirements'):
                    reqs = payment_required.payment_requirements
                    if reqs and len(reqs) > 0:
                        amount = float(reqs[0].max_amount_required) / 1e6  # USDC has 6 decimals
                elif hasattr(payment_required, 'maxAmountRequired'):
                    amount = float(payment_required.maxAmountRequired) / 1e6
            except Exception:
                pass

            receipt = PaymentReceipt(
                tx_id=hashlib.sha256(payload_b64.encode()).hexdigest()[:66],
                amount_usdc=amount,
                payer=self.wallet_address,
                payee="x402-endpoint",
                network=self.network,
                endpoint=url,
                timestamp=datetime.now(timezone.utc).isoformat(),
                x402_version=2,
                scheme="exact",
                settlement_tx=settlement_header[:66] if settlement_header else "",
            )

            self.total_spent += amount
            self.payment_count += 1
            self.payments.append(receipt)

            try:
                data = resp2.json()
            except Exception:
                data = {"raw": resp2.text}

            return X402Response(
                status_code=200,
                data=data,
                payment=receipt,
                paid=True,
                mode="real",
            )
        else:
            return X402Response(
                status_code=resp2.status_code,
                data={"error": f"Payment rejected: {resp2.text[:200]}"},
                paid=False,
                mode="real",
            )

    def get_wallet_status(self) -> dict:
        return {
            "wallet_address": self.wallet_address,
            "network": self.network,
            "total_spent_usdc": round(self.total_spent, 4),
            "payment_count": self.payment_count,
            "mode": "real",
        }


# ─── Simulation Client ───────────────────────────────────────────────

class SimulatedX402Client:
    """
    Simulated x402 client for demos without a real wallet.

    Simulates the full x402 flow:
    GET /endpoint → 402 Payment Required → auto-pay → data returned

    Use this when:
    - No private key available
    - Running demos without testnet USDC
    - Development and testing
    """

    def __init__(self, wallet_address: str = None, network: str = "eip155:8453"):
        self.wallet_address = wallet_address or f"0x{random.randbytes(20).hex()}"
        self.network = network
        self.balance_usdc = 10.00
        self.total_spent = 0.0
        self.payment_count = 0
        self.payments: list[PaymentReceipt] = []

    def _generate_tx_id(self) -> str:
        return f"0x{random.randbytes(32).hex()}"

    def _simulate_market_data(self, token_id: str) -> dict:
        """Generate realistic market data for a token."""
        base_prices = {
            "ethereum": 2650, "bitcoin": 95000, "solana": 180,
            "tidb-cloud": 0, "default": 100,
        }
        base = base_prices.get(token_id, base_prices["default"])
        price = base + random.uniform(-base * 0.03, base * 0.03)

        return {
            "id": token_id,
            "symbol": token_id[:3],
            "market_data": {
                "current_price": {"usd": round(price, 2)},
                "price_change_24h": round(random.uniform(-base * 0.05, base * 0.05), 2),
                "price_change_percentage_24h": round(random.uniform(-5, 5), 2),
                "high_24h": {"usd": round(price + random.uniform(base * 0.01, base * 0.05), 2)},
                "low_24h": {"usd": round(price - random.uniform(base * 0.01, base * 0.05), 2)},
                "market_cap": {"usd": round(price * random.uniform(1e8, 5e8), 0)},
                "total_volume": {"usd": round(random.uniform(1e9, 30e9), 0)},
            },
            "volatility": {
                "volatility_24h": round(random.uniform(1.5, 6.0), 2),
                "volatility_7d": round(random.uniform(3.0, 12.0), 2),
                "fear_greed_index": random.randint(20, 80),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def request(self, endpoint: str, cost_usdc: float = 0.01) -> X402Response:
        """Simulate x402 payment flow."""
        if self.balance_usdc < cost_usdc:
            return X402Response(
                status_code=402,
                data={"error": "Insufficient USDC balance", "required": cost_usdc, "balance": self.balance_usdc},
                paid=False,
                mode="simulation",
            )

        payee = f"0x{random.randbytes(20).hex()}"
        receipt = PaymentReceipt(
            tx_id=self._generate_tx_id(),
            amount_usdc=cost_usdc,
            payer=self.wallet_address,
            payee=payee,
            network=self.network,
            endpoint=endpoint,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gas_fee=0.0,
            x402_version=2,
            scheme="exact",
        )

        self.balance_usdc -= cost_usdc
        self.total_spent += cost_usdc
        self.payment_count += 1
        self.payments.append(receipt)

        # Extract token from endpoint
        token_id = "ethereum"
        for t in ["ethereum", "bitcoin", "solana"]:
            if t in endpoint.lower():
                token_id = t
                break

        return X402Response(
            status_code=200,
            data=self._simulate_market_data(token_id),
            payment=receipt,
            paid=True,
            mode="simulation",
        )

    def get_wallet_status(self) -> dict:
        return {
            "wallet_address": self.wallet_address,
            "network": self.network,
            "balance_usdc": round(self.balance_usdc, 4),
            "total_spent_usdc": round(self.total_spent, 4),
            "payment_count": self.payment_count,
            "mode": "simulation",
        }


# ─── Factory ─────────────────────────────────────────────────────────

def create_x402_client(
    mode: str = "auto",
    private_key: str = None,
    network: str = None,
) -> "RealX402Client | SimulatedX402Client":
    """
    Create an x402 client.

    Args:
        mode: "real", "simulation", or "auto"
              - "real": Uses actual x402 protocol (requires private key)
              - "simulation": Simulates payments (no wallet needed)
              - "auto": Uses real if PRIVATE_KEY is set, otherwise simulation
        private_key: EVM private key (hex string with 0x prefix)
        network: Network identifier (default: eip155:84532 for Base Sepolia)
    """
    pk = private_key or os.environ.get("PRIVATE_KEY")

    if mode == "auto":
        mode = "real" if pk else "simulation"

    if mode == "real":
        return RealX402Client(private_key=pk, network=network)
    else:
        return SimulatedX402Client(network=network or "eip155:8453")


# ─── Backward compatibility ──────────────────────────────────────────
# Keep X402Client as alias for SimulatedX402Client for existing code
X402Client = SimulatedX402Client
