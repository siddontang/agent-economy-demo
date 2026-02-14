"""
x402 Payment Protocol Client
==============================
Simulates the x402 machine payment flow:
1. Request data from an API
2. Receive 402 Payment Required
3. Auto-pay with USDC
4. Receive data

In production, this would integrate with:
- Coinbase Agentic Wallets (authenticate/fund/send/trade/earn skills)
- x402 protocol (HTTP 402 → USDC payment → data)
- Stripe Machine Payments (pay-per-use USDC)

Note: This demo simulates the payment flow. For real x402 integration,
see https://www.x402.org/ and Coinbase Developer Platform docs.
"""

import time
import json
import random
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone


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
    gas_fee: float = 0.0  # Gasless on Base

    def to_dict(self):
        return asdict(self)


@dataclass
class X402Response:
    """Response after successful x402 payment."""
    status_code: int
    data: dict
    payment: Optional[PaymentReceipt] = None
    paid: bool = False


class X402Client:
    """
    Client for x402 pay-per-use data access.

    Simulates the flow:
    GET /endpoint → 402 Payment Required → auto-pay → data returned

    Compatible with:
    - CoinGecko x402 endpoints ($0.01 USDC/request)
    - Any x402-enabled API
    """

    def __init__(self, wallet_address: str = None, network: str = "base"):
        self.wallet_address = wallet_address or f"0x{random.randbytes(20).hex()}"
        self.network = network
        self.balance_usdc = 10.00  # Starting balance
        self.total_spent = 0.0
        self.payment_count = 0
        self.payments: list[PaymentReceipt] = []

    def _generate_tx_id(self) -> str:
        return f"0x{random.randbytes(32).hex()}"

    def _simulate_market_data(self) -> dict:
        """Generate realistic ETH market data."""
        base_price = 2650 + random.uniform(-200, 200)
        return {
            "id": "ethereum",
            "symbol": "eth",
            "name": "Ethereum",
            "market_data": {
                "current_price": {"usd": round(base_price, 2)},
                "price_change_24h": round(random.uniform(-150, 150), 2),
                "price_change_percentage_24h": round(random.uniform(-5, 5), 2),
                "high_24h": {"usd": round(base_price + random.uniform(50, 200), 2)},
                "low_24h": {"usd": round(base_price - random.uniform(50, 200), 2)},
                "market_cap": {"usd": round(base_price * 120_000_000, 0)},
                "total_volume": {"usd": round(random.uniform(8e9, 20e9), 0)},
            },
            "volatility": {
                "volatility_24h": round(random.uniform(1.5, 6.0), 2),
                "volatility_7d": round(random.uniform(3.0, 12.0), 2),
                "fear_greed_index": random.randint(20, 80),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _simulate_multi_token_data(self) -> dict:
        """Generate data for multiple tokens."""
        tokens = {
            "bitcoin": {"symbol": "btc", "base": 95000},
            "ethereum": {"symbol": "eth", "base": 2650},
            "solana": {"symbol": "sol", "base": 180},
        }
        result = {}
        for token_id, info in tokens.items():
            price = info["base"] + random.uniform(-info["base"] * 0.03, info["base"] * 0.03)
            result[token_id] = {
                "symbol": info["symbol"],
                "price_usd": round(price, 2),
                "change_24h_pct": round(random.uniform(-5, 5), 2),
                "volume_24h": round(random.uniform(1e9, 30e9), 0),
            }
        return {
            "tokens": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def request(self, endpoint: str, cost_usdc: float = 0.01) -> X402Response:
        """
        Make a request to an x402-enabled endpoint.

        Flow:
        1. Send request
        2. Receive 402 Payment Required
        3. Auto-pay with USDC
        4. Receive data
        """
        # Step 1: Check balance
        if self.balance_usdc < cost_usdc:
            return X402Response(
                status_code=402,
                data={"error": "Insufficient USDC balance", "required": cost_usdc, "balance": self.balance_usdc},
                paid=False,
            )

        # Step 2: Simulate 402 → payment → data flow
        # In production: Coinbase Agentic Wallet would handle this automatically
        payee = f"0x{random.randbytes(20).hex()}"

        receipt = PaymentReceipt(
            tx_id=self._generate_tx_id(),
            amount_usdc=cost_usdc,
            payer=self.wallet_address,
            payee=payee,
            network=self.network,
            endpoint=endpoint,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gas_fee=0.0,  # Gasless on Base
        )

        # Step 3: Deduct balance and record
        self.balance_usdc -= cost_usdc
        self.total_spent += cost_usdc
        self.payment_count += 1
        self.payments.append(receipt)

        # Step 4: Return data based on endpoint
        if "coins/ethereum" in endpoint or "eth" in endpoint.lower():
            data = self._simulate_market_data()
        elif "market" in endpoint.lower() or "multi" in endpoint.lower():
            data = self._simulate_multi_token_data()
        else:
            data = self._simulate_market_data()

        return X402Response(
            status_code=200,
            data=data,
            payment=receipt,
            paid=True,
        )

    def get_wallet_status(self) -> dict:
        return {
            "wallet_address": self.wallet_address,
            "network": self.network,
            "balance_usdc": round(self.balance_usdc, 4),
            "total_spent_usdc": round(self.total_spent, 4),
            "payment_count": self.payment_count,
        }
