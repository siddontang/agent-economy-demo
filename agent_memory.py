"""
Agent Memory Layer — Powered by TiDB Cloud Zero
=================================================
Provides persistent memory for AI agents:
- Market data history (queryable with SQL)
- Payment audit trail (every micro-payment logged)
- Strategy state machine (decisions + reasoning)
- Cross-agent collaboration state

"Wallet gives agents capital. TiDB Cloud Zero gives agents memory."
"""

import json
import pymysql
from datetime import datetime, timezone


class AgentMemory:
    """
    Persistent memory layer for AI agents using TiDB Cloud Zero.

    Why TiDB Cloud Zero?
    - Instant provisioning (2 seconds, no signup)
    - MySQL compatible (works with every language/framework)
    - Distributed SQL (scales with your agent fleet)
    - Vector search (semantic memory retrieval)
    - Disposable by design (3-day TTL, zero cleanup)
    """

    def __init__(self, connection):
        self.conn = connection
        self._init_schema()

    def _init_schema(self):
        """Create the agent memory schema."""
        cur = self.conn.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS agent_economy")
        cur.execute("USE agent_economy")

        # Market data history
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                token_id VARCHAR(32) NOT NULL,
                price_usd DECIMAL(20, 2) NOT NULL,
                change_24h_pct DECIMAL(8, 2),
                volume_24h DECIMAL(20, 0),
                volatility_24h DECIMAL(8, 2),
                fear_greed_index INT,
                raw_data JSON,
                source VARCHAR(64) DEFAULT 'coingecko_x402',
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_token_time (token_id, fetched_at),
                INDEX idx_price (token_id, price_usd)
            )
        """)

        # Payment audit trail
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payment_log (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                tx_id VARCHAR(66) NOT NULL UNIQUE,
                amount_usdc DECIMAL(10, 4) NOT NULL,
                payer VARCHAR(42) NOT NULL,
                payee VARCHAR(42) NOT NULL,
                network VARCHAR(16) NOT NULL,
                endpoint VARCHAR(255) NOT NULL,
                status VARCHAR(16) DEFAULT 'confirmed',
                gas_fee DECIMAL(10, 6) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_payer (payer),
                INDEX idx_time (created_at)
            )
        """)

        # Strategy state & decisions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_log (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                agent_id VARCHAR(64) NOT NULL,
                action_type ENUM('alert', 'recommendation', 'execution', 'observation') NOT NULL,
                token_id VARCHAR(32),
                signal_name VARCHAR(64),
                signal_value DECIMAL(20, 4),
                decision TEXT NOT NULL,
                reasoning TEXT,
                confidence DECIMAL(3, 2),
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_agent_time (agent_id, created_at),
                INDEX idx_action (action_type)
            )
        """)

        # Agent collaboration state
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_state (
                agent_id VARCHAR(64) PRIMARY KEY,
                agent_type VARCHAR(32) NOT NULL,
                status ENUM('active', 'idle', 'error') DEFAULT 'active',
                wallet_address VARCHAR(42),
                balance_usdc DECIMAL(10, 4),
                total_spent_usdc DECIMAL(10, 4) DEFAULT 0,
                tasks_completed INT DEFAULT 0,
                config JSON,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_type (agent_type)
            )
        """)

    def store_market_data(self, token_id: str, data: dict) -> int:
        """Store market data fetched via x402 payment."""
        cur = self.conn.cursor()
        market = data.get("market_data", data)

        price = market.get("current_price", {}).get("usd") or data.get("price_usd", 0)
        change = market.get("price_change_percentage_24h") or data.get("change_24h_pct", 0)
        volume = market.get("total_volume", {}).get("usd") or data.get("volume_24h", 0)
        volatility = data.get("volatility", {}).get("volatility_24h")
        fgi = data.get("volatility", {}).get("fear_greed_index")

        cur.execute("""
            INSERT INTO market_data
            (token_id, price_usd, change_24h_pct, volume_24h, volatility_24h, fear_greed_index, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (token_id, price, change, volume, volatility, fgi, json.dumps(data)))

        return cur.lastrowid

    def log_payment(self, receipt) -> int:
        """Log an x402 micro-payment to the audit trail."""
        cur = self.conn.cursor()
        r = receipt if isinstance(receipt, dict) else receipt.to_dict()
        cur.execute("""
            INSERT INTO payment_log
            (tx_id, amount_usdc, payer, payee, network, endpoint, status, gas_fee)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (r["tx_id"], r["amount_usdc"], r["payer"], r["payee"],
              r["network"], r["endpoint"], r["status"], r["gas_fee"]))
        return cur.lastrowid

    def log_strategy(self, agent_id: str, action_type: str, decision: str,
                     token_id: str = None, signal_name: str = None,
                     signal_value: float = None, reasoning: str = None,
                     confidence: float = None, metadata: dict = None) -> int:
        """Log a strategy decision with reasoning."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO strategy_log
            (agent_id, action_type, token_id, signal_name, signal_value,
             decision, reasoning, confidence, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (agent_id, action_type, token_id, signal_name, signal_value,
              decision, reasoning, confidence,
              json.dumps(metadata) if metadata else None))
        return cur.lastrowid

    def register_agent(self, agent_id: str, agent_type: str,
                       wallet_address: str = None, config: dict = None):
        """Register an agent in the collaboration state."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO agent_state (agent_id, agent_type, wallet_address, config)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            status = 'active', last_heartbeat = NOW()
        """, (agent_id, agent_type, wallet_address,
              json.dumps(config) if config else None))

    def update_agent_spending(self, agent_id: str, balance: float, total_spent: float):
        """Update agent's wallet status."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE agent_state
            SET balance_usdc = %s, total_spent_usdc = %s, last_heartbeat = NOW()
            WHERE agent_id = %s
        """, (balance, total_spent, agent_id))

    def get_price_history(self, token_id: str, limit: int = 10) -> list:
        """Retrieve recent price history from memory."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT price_usd, change_24h_pct, volatility_24h, fear_greed_index, fetched_at
            FROM market_data
            WHERE token_id = %s
            ORDER BY fetched_at DESC
            LIMIT %s
        """, (token_id, limit))
        return cur.fetchall()

    def get_spending_summary(self) -> dict:
        """Get payment audit summary."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total_payments,
                SUM(amount_usdc) as total_spent,
                AVG(amount_usdc) as avg_payment,
                COUNT(DISTINCT endpoint) as unique_endpoints,
                COUNT(DISTINCT payer) as unique_agents
            FROM payment_log
        """)
        row = cur.fetchone()
        return {
            "total_payments": row[0],
            "total_spent_usdc": float(row[1] or 0),
            "avg_payment_usdc": float(row[2] or 0),
            "unique_endpoints": row[3],
            "unique_agents": row[4],
        }

    def get_strategy_summary(self, agent_id: str = None) -> list:
        """Get recent strategy decisions."""
        cur = self.conn.cursor()
        query = """
            SELECT agent_id, action_type, token_id, decision, confidence, created_at
            FROM strategy_log
        """
        params = []
        if agent_id:
            query += " WHERE agent_id = %s"
            params.append(agent_id)
        query += " ORDER BY created_at DESC LIMIT 20"
        cur.execute(query, params)
        return cur.fetchall()

    def get_dashboard(self) -> dict:
        """Get a full dashboard view of the agent economy state."""
        cur = self.conn.cursor()

        # Market data stats
        cur.execute("""
            SELECT token_id,
                   COUNT(*) as data_points,
                   ROUND(AVG(price_usd), 2) as avg_price,
                   ROUND(MIN(price_usd), 2) as min_price,
                   ROUND(MAX(price_usd), 2) as max_price
            FROM market_data
            GROUP BY token_id
        """)
        market_stats = cur.fetchall()

        # Agent stats
        cur.execute("""
            SELECT agent_id, agent_type, status,
                   ROUND(balance_usdc, 4) as balance,
                   ROUND(total_spent_usdc, 4) as spent
            FROM agent_state
        """)
        agents = cur.fetchall()

        # Strategy stats
        cur.execute("""
            SELECT action_type, COUNT(*) as count
            FROM strategy_log
            GROUP BY action_type
        """)
        strategy_stats = cur.fetchall()

        return {
            "market_stats": market_stats,
            "agents": agents,
            "strategy_stats": strategy_stats,
            "spending": self.get_spending_summary(),
        }
