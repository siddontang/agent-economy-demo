"""
x402 Payment Protocol Client
==============================
Implements the x402 HTTP-native payment protocol:

1. Client sends HTTP request to x402-enabled endpoint
2. Server responds 402 + PAYMENT-REQUIRED header (base64 JSON)
3. Client signs EIP-712 payment authorization with wallet
4. Client resends with PAYMENT-SIGNATURE header
5. Server verifies, settles on-chain, returns data + PAYMENT-RESPONSE

Live mode uses the official Coinbase x402 SDK (pip install "x402[requests,evm]").
Simulation mode works without any extra dependencies.

References:
- Protocol spec: https://x402.org
- GitHub: https://github.com/coinbase/x402
- Facilitator: https://x402.org/facilitator
"""

import json
import random
from dataclasses import dataclass, asdict
from typing import Optional, List
from datetime import datetime, timezone

import requests

# ─── Constants ───────────────────────────────────────────────────────
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"
X_PAYMENT_RESPONSE_HEADER = "X-PAYMENT-RESPONSE"  # V1 legacy

# Base network (EIP-155 chain ID 8453)
BASE_MAINNET = "eip155:8453"
BASE_TESTNET = "eip155:84532"

# USDC contract addresses
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# CoinGecko x402 endpoint (real, pay-per-request)
COINGECKO_X402_BASE = "https://pro-api.coingecko.com/api/v3/x402"


# ─── Data Classes ────────────────────────────────────────────────────

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
    settlement_response: Optional[dict] = None

    def to_dict(self):
        d = asdict(self)
        if d.get("settlement_response") is None:
            d.pop("settlement_response", None)
        return d


@dataclass
class X402Response:
    """Response after x402 payment flow."""
    status_code: int
    data: dict
    payment: Optional[PaymentReceipt] = None
    paid: bool = False
    headers: Optional[dict] = None


# ─── Official x402 SDK wrapper ──────────────────────────────────────

def _create_x402_session(private_key: str):
    """
    Create an x402-enabled requests session using the official Coinbase SDK.

    Requires: pip install "x402[requests,evm]"
    Returns: (session, wallet_address) or raises ImportError
    """
    from eth_account import Account
    from x402 import x402ClientSync
    from x402.http.clients import x402_requests
    from x402.mechanisms.evm import EthAccountSigner
    from x402.mechanisms.evm.exact import register_exact_evm_client

    account = Account.from_key(private_key)
    client = x402ClientSync()
    register_exact_evm_client(client, EthAccountSigner(account))
    session = x402_requests(client)
    return session, account.address


# ─── x402 Client ─────────────────────────────────────────────────────

class X402Client:
    """
    x402 payment protocol client.

    Modes:
    - LIVE: Uses the official Coinbase x402 SDK for real on-chain payments.
      The SDK handles 402 detection, EIP-712 signing, and retry automatically.
      Requires: pip install "x402[requests,evm]"

    - SIMULATION: Realistic protocol flow with simulated data.
      No extra dependencies needed.

    Usage:
        # Live mode (requires private key + x402 SDK)
        client = X402Client(private_key="0x...", mode="live")
        response = client.request("https://pro-api.coingecko.com/api/v3/x402/simple/price?ids=ethereum&vs_currencies=usd")

        # Simulation mode (for demos)
        client = X402Client(mode="simulation")
        response = client.request("coingecko.com/api/v3/coins/ethereum")
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        network: str = "base",
        mode: str = "auto",  # "live", "simulation", "auto"
    ):
        self.network = network
        self.network_id = BASE_MAINNET if network == "base" else BASE_TESTNET
        self.mode = mode
        self._has_sdk = False

        # Tracking
        self.balance_usdc = 10.00
        self.total_spent = 0.0
        self.payment_count = 0
        self.payments: List[PaymentReceipt] = []

        # Try to set up the official x402 SDK session
        if private_key:
            try:
                self._x402_session, self.wallet_address = _create_x402_session(private_key)
                self._has_sdk = True
            except ImportError:
                # SDK not installed — fall back to simulation
                self.wallet_address = "0x" + private_key[-40:] if len(private_key) >= 42 else f"0x{random.randbytes(20).hex()}"
                self._x402_session = None
        else:
            self.wallet_address = f"0x{random.randbytes(20).hex()}"
            self._x402_session = None

        # Plain session for simulation mode
        self._session = requests.Session()

    @property
    def is_live(self) -> bool:
        """Whether this client can make real x402 payments."""
        return self._has_sdk

    def request(self, endpoint: str, cost_usdc: float = 0.01, **kwargs) -> X402Response:
        """
        Make a request to an x402-enabled endpoint.

        In live mode: The official SDK handles 402→sign→pay→retry automatically.
        In simulation mode: Simulates the full protocol flow with realistic data.
        """
        if self._should_use_live(endpoint):
            return self._request_live(endpoint, cost_usdc, **kwargs)
        else:
            return self._request_simulated(endpoint, cost_usdc)

    def _should_use_live(self, endpoint: str) -> bool:
        """Determine whether to use live x402 for this request."""
        if not self._has_sdk:
            return False
        if self.mode == "live":
            return True
        if self.mode == "auto" and endpoint.startswith("http"):
            return True
        return False

    def _request_live(self, url: str, cost_usdc: float, **kwargs) -> X402Response:
        """
        Real x402 request using the official Coinbase SDK.

        The SDK's x402_requests session automatically:
        1. Sends GET → receives 402 + PAYMENT-REQUIRED header
        2. Signs EIP-712 payment with the registered EVM signer
        3. Resends with PAYMENT-SIGNATURE header
        4. Returns the final response (200 with data)
        """
        try:
            resp = self._x402_session.get(url, timeout=30, **kwargs)

            if resp.status_code == 200:
                # Parse settlement from response headers
                settle_header = (
                    resp.headers.get(PAYMENT_RESPONSE_HEADER) or
                    resp.headers.get(X_PAYMENT_RESPONSE_HEADER)
                )
                settlement = None
                if settle_header:
                    try:
                        from x402.http import decode_payment_response_header
                        pr = decode_payment_response_header(settle_header)
                        settlement = pr.model_dump() if hasattr(pr, "model_dump") else pr
                    except Exception:
                        pass

                # Determine if a payment was made (settlement header present)
                paid = settlement is not None
                # Extract tx hash from settlement, with unique suffix to avoid
                # duplicate key errors when facilitator batches settlements
                base_tx = ""
                if settlement:
                    base_tx = (
                        settlement.get("transaction", "") or
                        settlement.get("txHash", "") or
                        settlement.get("tx_hash", "")
                    )
                if not base_tx:
                    base_tx = f"0x{random.randbytes(32).hex()}"
                tx_id = f"{base_tx}:{self.payment_count}"

                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:1000]}

                receipt = None
                if paid:
                    receipt = self._record_payment(
                        endpoint=url,
                        cost_usdc=cost_usdc,
                        tx_id=tx_id,
                        payee="x402-facilitator",
                        settlement=settlement,
                    )

                return X402Response(
                    status_code=200,
                    data=data,
                    payment=receipt,
                    paid=paid,
                    headers=dict(resp.headers),
                )

            elif resp.status_code == 402:
                # SDK failed to handle payment (insufficient funds, etc.)
                return X402Response(
                    status_code=402,
                    data={"error": "Payment required but SDK could not complete payment",
                          "body": resp.text[:500]},
                )

            else:
                return X402Response(
                    status_code=resp.status_code,
                    data={"error": f"HTTP {resp.status_code}", "body": resp.text[:500]},
                )

        except Exception as e:
            return X402Response(
                status_code=0,
                data={"error": f"x402 request failed: {str(e)}"},
            )

    def _request_simulated(self, endpoint: str, cost_usdc: float) -> X402Response:
        """
        Simulated x402 flow with realistic protocol behavior.
        Used when no live x402 endpoint or SDK is available.
        """
        if self.balance_usdc < cost_usdc:
            return X402Response(
                status_code=402,
                data={"error": "Insufficient USDC balance", "required": cost_usdc, "balance": self.balance_usdc},
            )

        # Simulate settlement
        payee = f"0x{random.randbytes(20).hex()}"
        tx_id = f"0x{random.randbytes(32).hex()}"
        settlement = {
            "txHash": tx_id,
            "network": self.network_id,
            "success": True,
            "payer": self.wallet_address,
            "payee": payee,
            "amount": str(int(cost_usdc * 1e6)),
            "token": USDC_BASE,
        }

        receipt = self._record_payment(
            endpoint=endpoint,
            cost_usdc=cost_usdc,
            tx_id=tx_id,
            payee=payee,
            settlement=settlement,
        )

        # Return simulated market data
        data = self._generate_market_data(endpoint)

        return X402Response(
            status_code=200,
            data=data,
            payment=receipt,
            paid=True,
        )

    def _record_payment(self, endpoint: str, cost_usdc: float, tx_id: str,
                        payee: str, settlement: dict = None) -> PaymentReceipt:
        """Record a payment in the client's ledger."""
        receipt = PaymentReceipt(
            tx_id=tx_id,
            amount_usdc=cost_usdc,
            payer=self.wallet_address,
            payee=payee,
            network=self.network,
            endpoint=endpoint,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gas_fee=0.0,  # Gasless on Base
            settlement_response=settlement,
        )

        self.balance_usdc -= cost_usdc
        self.total_spent += cost_usdc
        self.payment_count += 1
        self.payments.append(receipt)
        return receipt

    def _generate_market_data(self, endpoint: str) -> dict:
        """Generate realistic market data for simulation mode."""
        token_map = {
            "bitcoin": {"symbol": "btc", "base": 95000},
            "ethereum": {"symbol": "eth", "base": 2650},
            "solana": {"symbol": "sol", "base": 180},
        }

        # Detect token from endpoint
        token_id = "ethereum"
        for t in token_map:
            if t in endpoint.lower():
                token_id = t
                break

        info = token_map.get(token_id, {"symbol": "eth", "base": 2650})
        base_price = info["base"] + random.uniform(-info["base"] * 0.05, info["base"] * 0.05)

        return {
            "id": token_id,
            "symbol": info["symbol"],
            "name": token_id.capitalize(),
            "market_data": {
                "current_price": {"usd": round(base_price, 2)},
                "price_change_24h": round(random.uniform(-info["base"] * 0.05, info["base"] * 0.05), 2),
                "price_change_percentage_24h": round(random.uniform(-5, 5), 2),
                "high_24h": {"usd": round(base_price + random.uniform(0, info["base"] * 0.03), 2)},
                "low_24h": {"usd": round(base_price - random.uniform(0, info["base"] * 0.03), 2)},
                "market_cap": {"usd": round(base_price * (120_000_000 if token_id == "ethereum" else 21_000_000 if token_id == "bitcoin" else 400_000_000), 0)},
                "total_volume": {"usd": round(random.uniform(8e9, 20e9), 0)},
            },
            "volatility": {
                "volatility_24h": round(random.uniform(1.5, 6.0), 2),
                "volatility_7d": round(random.uniform(3.0, 12.0), 2),
                "fear_greed_index": random.randint(20, 80),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "x402": {
                "paid": True,
                "cost_usdc": 0.01,
                "protocol_version": 2,
                "network": self.network_id,
            },
        }

    def get_wallet_status(self) -> dict:
        return {
            "wallet_address": self.wallet_address,
            "network": self.network,
            "network_id": self.network_id,
            "balance_usdc": round(self.balance_usdc, 4),
            "total_spent_usdc": round(self.total_spent, 4),
            "payment_count": self.payment_count,
            "mode": self.mode,
            "has_real_signer": self._has_sdk,
        }
