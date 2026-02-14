#!/usr/bin/env python3
"""
Agent Economy Demo
===================
Wallet gives agents capital. TiDB Cloud Zero gives agents memory.

Demonstrates:
1. Agent pays for market data via x402 protocol ($0.01 USDC/request)
2. Agent stores data + decisions in TiDB Cloud Zero (instant, no signup)
3. Agent analyzes trends and generates alerts
4. Full audit trail: every payment, every decision, queryable with SQL

Usage:
    python demo.py                              # Full demo
    python demo.py --connection-string "mysql://..."  # Reuse existing DB
"""

import json
import sys
import time
import random
import argparse
import requests

from x402_client import X402Client
from agent_memory import AgentMemory
from market_agent import MarketAgent

# ─── Config ──────────────────────────────────────────────────────────
INVITATION_CODE = "TIPLANET"
API_URL = "https://zero.tidbapi.com/v1alpha1/instances"

# ─── Colors ──────────────────────────────────────────────────────────
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║       🤖💰 Agent Economy Demo: Pay, Remember, Act           ║
║                                                              ║
║   Wallet gives agents capital.                               ║
║   TiDB Cloud Zero gives agents memory.                      ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def provision_database(tag="agent-economy-demo"):
    """Provision a TiDB Cloud Zero database."""
    print(f"{YELLOW}⏳ Provisioning TiDB Cloud Zero database...{RESET}")
    start = time.time()

    resp = requests.post(API_URL, json={
        "invitationCode": INVITATION_CODE,
        "tag": tag,
    })
    resp.raise_for_status()
    data = resp.json()
    elapsed = time.time() - start
    instance = data["instance"]
    conn = instance["connection"]

    print(f"{GREEN}✅ Database ready in {elapsed:.1f}s — no signup, no config!{RESET}")
    print(f"   Host:     {conn['host']}")
    print(f"   Expires:  {instance['expiresAt']}")
    print()
    return instance


def get_connection(instance):
    """Create a PyMySQL connection."""
    import pymysql
    conn_info = instance["connection"]
    return pymysql.connect(
        host=conn_info["host"],
        port=conn_info["port"],
        user=conn_info["username"],
        password=conn_info["password"],
        ssl={"ca": None},
        ssl_verify_cert=False,
        autocommit=True,
    )


def phase_1_setup(memory, wallet):
    """Phase 1: Initialize the agent with a wallet and memory."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  Phase 1: Agent Initialization")
    print(f"  Setting up wallet (capital) + memory (TiDB Cloud Zero)")
    print(f"{'='*62}{RESET}\n")

    status = wallet.get_wallet_status()
    print(f"  {MAGENTA}💰 Wallet initialized{RESET}")
    print(f"     Address:  {status['wallet_address'][:10]}...{status['wallet_address'][-8:]}")
    print(f"     Network:  {status['network']} (gasless)")
    print(f"     Balance:  ${status['balance_usdc']:.2f} USDC")
    print()
    print(f"  {GREEN}🧠 Memory initialized (TiDB Cloud Zero){RESET}")
    print(f"     Tables: market_data, payment_log, strategy_log, agent_state")
    print(f"     Ready for: data storage, audit trail, strategy decisions")
    print()


def phase_2_pay_and_remember(agent):
    """Phase 2: Agent pays for data and stores it in memory."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  Phase 2: Pay for Data → Store in Memory")
    print(f"  x402 protocol: HTTP 402 → USDC payment → data returned")
    print(f"{'='*62}{RESET}\n")

    tokens = ["ethereum", "bitcoin", "solana"]
    cycles = 3

    for cycle in range(1, cycles + 1):
        print(f"  {YELLOW}── Cycle {cycle}/{cycles} ──{RESET}")

        for token in tokens:
            # Simulate the x402 flow visually
            endpoint = f"coingecko.com/api/v3/coins/{token}"
            print(f"  {DIM}GET /{token} → 402 Payment Required{RESET}")

            data = agent.fetch_and_store(token)

            if "error" in data:
                print(f"  {RED}❌ Payment failed: {data['error']}{RESET}")
                continue

            market = data.get("market_data", data)
            price = market.get("current_price", {}).get("usd") or data.get("price_usd", 0)
            print(f"  {GREEN}✅ Paid $0.01 USDC → {token.upper()} ${price:,.2f}{RESET}")

        wallet = agent.wallet.get_wallet_status()
        print(f"  {DIM}   Balance: ${wallet['balance_usdc']:.2f} | Spent: ${wallet['total_spent_usdc']:.2f} | Payments: {wallet['payment_count']}{RESET}")
        print()
        time.sleep(0.3)

    print(f"  {GREEN}✅ {agent.wallet.payment_count} data purchases stored in TiDB Cloud Zero{RESET}\n")


def phase_3_analyze_and_act(agent):
    """Phase 3: Agent analyzes data and generates decisions."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  Phase 3: Analyze → Decide → Act")
    print(f"  Every decision logged to TiDB Cloud Zero (auditable)")
    print(f"{'='*62}{RESET}\n")

    tokens = ["ethereum", "bitcoin", "solana"]

    for token in tokens:
        data = agent.fetch_and_store(token)
        if "error" in data:
            continue

        decisions = agent.analyze_and_decide(token, data)
        for d in decisions:
            print(f"  {d}")
    print()


def phase_4_audit_dashboard(memory, wallet):
    """Phase 4: Query the audit trail — the power of SQL memory."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  Phase 4: Agent Economy Dashboard")
    print(f"  Everything queryable with SQL — that's the power of memory")
    print(f"{'='*62}{RESET}\n")

    dashboard = memory.get_dashboard()

    # Market overview
    print(f"  {CYAN}📊 Market Data Collected:{RESET}")
    for row in dashboard["market_stats"]:
        print(f"     {row[0]:12s}  {row[1]} points  avg=${row[2]:>10}  range=[${row[3]} — ${row[4]}]")
    print()

    # Spending audit
    spending = dashboard["spending"]
    print(f"  {MAGENTA}💰 Payment Audit Trail:{RESET}")
    print(f"     Total payments:    {spending['total_payments']}")
    print(f"     Total spent:       ${spending['total_spent_usdc']:.4f} USDC")
    print(f"     Avg per request:   ${spending['avg_payment_usdc']:.4f} USDC")
    print(f"     Unique endpoints:  {spending['unique_endpoints']}")
    print(f"     Unique agents:     {spending['unique_agents']}")
    print()

    # Strategy decisions
    print(f"  {YELLOW}🎯 Strategy Decisions:{RESET}")
    for row in dashboard["strategy_stats"]:
        icons = {"alert": "⚠️", "recommendation": "💡", "observation": "👀", "execution": "⚡"}
        print(f"     {icons.get(row[0], '•')} {row[0]:20s} {row[1]} decisions")
    print()

    # Agent state
    print(f"  {GREEN}🤖 Agent Fleet:{RESET}")
    for row in dashboard["agents"]:
        print(f"     {row[0]:20s} [{row[1]}] status={row[2]} balance=${row[3]} spent=${row[4]}")
    print()

    # Show raw SQL power
    print(f"  {DIM}── Example SQL queries you can run on this data ──{RESET}")
    queries = [
        "SELECT token_id, AVG(price_usd) FROM market_data GROUP BY token_id;",
        "SELECT SUM(amount_usdc) as total_cost FROM payment_log WHERE created_at > NOW() - INTERVAL 1 HOUR;",
        "SELECT * FROM strategy_log WHERE action_type = 'alert' ORDER BY created_at DESC LIMIT 5;",
        "SELECT agent_id, balance_usdc, total_spent_usdc FROM agent_state;",
    ]
    for q in queries:
        print(f"  {DIM}  > {q}{RESET}")
    print()


def phase_5_multi_agent(memory, conn):
    """Phase 5: Multi-agent collaboration via shared TiDB state."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  Phase 5: Multi-Agent Collaboration")
    print(f"  Agents share state through TiDB Cloud Zero")
    print(f"{'='*62}{RESET}\n")

    # Create multiple specialized agents
    agents_config = [
        ("monitor-eth", "market_monitor", ["ethereum"]),
        ("monitor-btc", "market_monitor", ["bitcoin"]),
        ("strategist", "strategy_engine", ["ethereum", "bitcoin", "solana"]),
    ]

    agents = []
    for agent_id, agent_type, tokens in agents_config:
        wallet = X402Client(network="base")
        agent = MarketAgent(agent_id, memory, wallet)
        agents.append((agent, tokens))
        print(f"  {GREEN}🤖 {agent_id}{RESET} [{agent_type}] monitoring {', '.join(tokens)}")

    print()
    print(f"  {YELLOW}⚡ All agents running simultaneously, sharing state via TiDB...{RESET}\n")

    # Each agent runs a cycle
    for agent, tokens in agents:
        result = agent.run_cycle(tokens)
        for d in result["decisions"]:
            print(f"  [{agent.agent_id}] {d}")

    print()

    # Show shared state
    print(f"  {CYAN}📊 Shared State (all agents can read/write):{RESET}")
    cur = conn.cursor()
    cur.execute("USE agent_economy")
    cur.execute("""
        SELECT agent_id, agent_type, status,
               ROUND(balance_usdc, 2) as balance,
               ROUND(total_spent_usdc, 2) as spent
        FROM agent_state
        ORDER BY agent_id
    """)
    for row in cur.fetchall():
        print(f"     {row[0]:20s} {row[1]:20s} ${row[3]:>6} balance  ${row[4]:>6} spent")

    print(f"\n  {GREEN}✅ Multi-agent collaboration via shared SQL state!{RESET}\n")


def summary():
    """Print the final summary."""
    print(f"{CYAN}{BOLD}{'='*62}")
    print(f"  🎉 Demo Complete!")
    print(f"{'='*62}{RESET}")
    print(f"""
{BOLD}What you just saw:{RESET}
  💰 Agent paid for market data via x402 ($0.01 USDC/request)
  🧠 Every data point stored in TiDB Cloud Zero
  🎯 Decisions logged with reasoning (auditable)
  🤖 Multiple agents collaborating via shared SQL state
  📊 Full dashboard queryable with standard SQL

{BOLD}The Agent Economy Stack:{RESET}
  ┌─────────────────────────────────────────────────┐
  │  💰 Capital Layer    │  Coinbase Agentic Wallets │
  │                      │  x402 / Stripe / USDC     │
  ├──────────────────────┼──────────────────────────-┤
  │  🧠 Memory Layer     │  TiDB Cloud Zero          │
  │                      │  SQL + Vector + JSON       │
  ├──────────────────────┼──────────────────────────-┤
  │  ⚡ Action Layer     │  Alerts / Strategy /       │
  │                      │  On-chain execution        │
  └──────────────────────┴──────────────────────────-┘

{BOLD}Key insight:{RESET}
  Wallet gives agents capital to act.
  TiDB Cloud Zero gives agents memory to remember.
  Together: agents that can pay, remember, and iterate.

{BOLD}Try it:{RESET}
  🔗 TiDB Cloud Zero: https://zero.tidbcloud.com/?code=TIPLANET#demo
  📖 Skill: https://zero.tidbcloud.com/SKILL.md

{BOLD}References:{RESET}
  • Coinbase Agentic Wallets: coinbase.com/developer-platform
  • x402 Protocol: x402.org
  • Stripe Machine Payments: docs.stripe.com/crypto/machine-payments
  • CoinGecko x402: docs.coingecko.com/reference/x402-introduction
""")


def main():
    parser = argparse.ArgumentParser(description="Agent Economy Demo")
    parser.add_argument("--connection-string", help="Reuse existing TiDB connection")
    args = parser.parse_args()

    banner()

    # Provision database
    if args.connection_string:
        from urllib.parse import urlparse
        parsed = urlparse(args.connection_string)
        instance = {
            "connection": {
                "host": parsed.hostname,
                "port": parsed.port or 4000,
                "username": parsed.username,
                "password": parsed.password,
            }
        }
    else:
        instance = provision_database()

    conn = get_connection(instance)
    print(f"{GREEN}✅ Connected to TiDB Cloud Zero{RESET}\n")

    # Initialize
    memory = AgentMemory(conn)
    wallet = X402Client(network="base")
    agent = MarketAgent("market-agent-01", memory, wallet)

    # Run all phases
    phase_1_setup(memory, wallet)
    phase_2_pay_and_remember(agent)
    phase_3_analyze_and_act(agent)
    phase_4_audit_dashboard(memory, wallet)
    phase_5_multi_agent(memory, conn)
    summary()

    conn.close()


if __name__ == "__main__":
    main()
