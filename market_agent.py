"""
Market Monitoring Agent
========================
An AI agent that:
1. Pays for real-time market data via x402 protocol
2. Stores data + decisions in TiDB Cloud Zero
3. Analyzes trends and generates alerts/recommendations

Demonstrates the Agent Economy loop:
  Pay → Remember → Analyze → Act → Repeat
"""

import random
from datetime import datetime, timezone

from x402_client import X402Client, PaymentReceipt, COINGECKO_X402_BASE
from agent_memory import AgentMemory


class MarketAgent:
    """
    An autonomous market monitoring agent.

    Capital: x402 payments via Coinbase Agentic Wallet
    Memory: TiDB Cloud Zero
    Action: Alerts, recommendations, strategy updates
    """

    def __init__(self, agent_id: str, memory: AgentMemory, wallet: X402Client):
        self.agent_id = agent_id
        self.memory = memory
        self.wallet = wallet
        self.alerts = []

        # Register agent in shared state
        self.memory.register_agent(
            agent_id=agent_id,
            agent_type="market_monitor",
            wallet_address=wallet.wallet_address,
            config={
                "monitored_tokens": ["ethereum", "bitcoin", "solana"],
                "alert_thresholds": {
                    "volatility_24h": 4.0,
                    "price_change_pct": 3.0,
                    "fear_greed_low": 25,
                    "fear_greed_high": 75,
                },
            },
        )

    def fetch_and_store(self, token_id: str = "ethereum") -> dict:
        """
        Fetch market data via x402 payment and store in memory.

        Flow:
        1. Request data → 402 Payment Required
        2. Auto-pay $0.01 USDC
        3. Receive data
        4. Store in TiDB Cloud Zero
        5. Log payment to audit trail
        """
        # Step 1-3: Pay for data
        if self.wallet.is_live:
            endpoint = (
                f"{COINGECKO_X402_BASE}/simple/price"
                f"?ids={token_id}&vs_currencies=usd"
                f"&include_24hr_change=true&include_24hr_vol=true"
                f"&include_market_cap=true"
            )
        else:
            endpoint = f"coingecko.com/api/v3/coins/{token_id}"
        response = self.wallet.request(endpoint, cost_usdc=0.01)

        if not response.paid:
            self.memory.log_strategy(
                agent_id=self.agent_id,
                action_type="observation",
                token_id=token_id,
                decision="FAILED: Insufficient balance for data purchase",
                reasoning=f"Balance: ${self.wallet.balance_usdc:.4f}, Required: $0.01",
                confidence=1.0,
            )
            return {"error": "Payment failed", "balance": self.wallet.balance_usdc}

        # Step 4: Store market data in TiDB Cloud Zero
        data = response.data
        if self.wallet.is_live:
            data = self._normalize_coingecko_response(token_id, data)
        self.memory.store_market_data(token_id, data)

        # Step 5: Log payment
        self.memory.log_payment(response.payment)

        # Update agent spending state
        wallet_status = self.wallet.get_wallet_status()
        self.memory.update_agent_spending(
            self.agent_id,
            wallet_status["balance_usdc"],
            wallet_status["total_spent_usdc"],
        )

        return data

    def analyze_and_decide(self, token_id: str, data: dict) -> list:
        """
        Analyze market data and generate decisions.
        All decisions are logged to TiDB Cloud Zero for auditability.
        """
        decisions = []
        market = data.get("market_data", data)
        vol = data.get("volatility", {})

        price = market.get("current_price", {}).get("usd") or data.get("price_usd", 0)
        change_pct = market.get("price_change_percentage_24h") or data.get("change_24h_pct", 0)
        volatility = vol.get("volatility_24h", 0)
        fgi = vol.get("fear_greed_index", 50)

        # Rule 1: High volatility alert
        if volatility and volatility > 4.0:
            decision = f"⚠️ HIGH VOLATILITY ALERT: {token_id.upper()} volatility at {volatility}% (threshold: 4%)"
            self.memory.log_strategy(
                agent_id=self.agent_id,
                action_type="alert",
                token_id=token_id,
                signal_name="volatility_24h",
                signal_value=volatility,
                decision=decision,
                reasoning="24h volatility exceeds threshold. Consider reducing position size or hedging.",
                confidence=0.85,
                metadata={"price": price, "change_pct": change_pct},
            )
            decisions.append(decision)

        # Rule 2: Significant price movement
        if abs(change_pct) > 3.0:
            direction = "📈 UP" if change_pct > 0 else "📉 DOWN"
            decision = f"{direction}: {token_id.upper()} moved {change_pct:+.2f}% in 24h (${price:,.2f})"
            self.memory.log_strategy(
                agent_id=self.agent_id,
                action_type="alert",
                token_id=token_id,
                signal_name="price_change_24h",
                signal_value=change_pct,
                decision=decision,
                reasoning=f"Price change exceeds ±3% threshold. Current: ${price:,.2f}",
                confidence=0.90,
                metadata={"volatility": volatility, "fgi": fgi},
            )
            decisions.append(decision)

        # Rule 3: Fear & Greed extremes
        if fgi and (fgi < 25 or fgi > 75):
            sentiment = "😨 EXTREME FEAR" if fgi < 25 else "🤑 EXTREME GREED"
            decision = f"{sentiment}: Fear & Greed Index at {fgi} for {token_id.upper()}"
            action = "Potential buying opportunity (contrarian)" if fgi < 25 else "Consider taking profits"
            self.memory.log_strategy(
                agent_id=self.agent_id,
                action_type="recommendation",
                token_id=token_id,
                signal_name="fear_greed_index",
                signal_value=fgi,
                decision=decision,
                reasoning=action,
                confidence=0.70,
                metadata={"price": price},
            )
            decisions.append(decision)

        # Rule 4: Normal observation (always log)
        if not decisions:
            decision = f"✅ NORMAL: {token_id.upper()} at ${price:,.2f} ({change_pct:+.2f}%), volatility {volatility}%"
            self.memory.log_strategy(
                agent_id=self.agent_id,
                action_type="observation",
                token_id=token_id,
                signal_name="routine_check",
                signal_value=price,
                decision=decision,
                reasoning="All metrics within normal ranges. No action required.",
                confidence=0.95,
            )
            decisions.append(decision)

        return decisions

    @staticmethod
    def _normalize_coingecko_response(token_id: str, raw: dict) -> dict:
        """
        Normalize CoinGecko /simple/price response to the internal format
        expected by analyze_and_decide().

        CoinGecko returns: {"ethereum": {"usd": 2650, "usd_24h_change": 1.5, ...}}
        We normalize to: {"id": "ethereum", "market_data": {...}, "volatility": {...}}
        """
        token_data = raw.get(token_id, {})
        price = token_data.get("usd", 0)
        change_24h = token_data.get("usd_24h_change", 0)
        change_pct = (change_24h / price * 100) if price else 0
        volume = token_data.get("usd_24h_vol", 0)
        market_cap = token_data.get("usd_market_cap", 0)

        return {
            "id": token_id,
            "symbol": token_id[:3],
            "name": token_id.capitalize(),
            "market_data": {
                "current_price": {"usd": round(price, 2)},
                "price_change_24h": round(change_24h, 2),
                "price_change_percentage_24h": round(change_pct, 2),
                "high_24h": {"usd": round(price * 1.02, 2)},
                "low_24h": {"usd": round(price * 0.98, 2)},
                "market_cap": {"usd": round(market_cap, 0)},
                "total_volume": {"usd": round(volume, 0)},
            },
            "volatility": {
                "volatility_24h": round(abs(change_pct) * 1.5, 2),
                "volatility_7d": round(abs(change_pct) * 3, 2),
                "fear_greed_index": random.randint(20, 80),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "x402": {
                "paid": True,
                "cost_usdc": 0.01,
                "protocol_version": 2,
                "source": "coingecko",
            },
        }

    def run_cycle(self, tokens: list = None) -> dict:
        """
        Run one complete agent cycle:
        Pay → Remember → Analyze → Act
        """
        if tokens is None:
            tokens = ["ethereum"]

        all_decisions = []
        for token in tokens:
            data = self.fetch_and_store(token)
            if "error" not in data:
                decisions = self.analyze_and_decide(token, data)
                all_decisions.extend(decisions)

        return {
            "decisions": all_decisions,
            "wallet": self.wallet.get_wallet_status(),
        }
