import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

# ============================================================
# REAL KiteConnect SDK — Zerodha Official Python Library
# ============================================================
try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    logging.warning("kiteconnect not installed. Run: pip install kiteconnect>=5.0.1")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class TradingEngine:
    def __init__(self):
        # user_id -> KiteConnect instance (real Zerodha SDK)
        self.active_sessions: Dict[str, "KiteConnect"] = {}
        # user_id -> {strategy_id -> settings dict}
        self.running_strategies: Dict[str, Dict[str, dict]] = {}
        # user_id -> live pnl cache (updated every tick)
        self.live_pnls: Dict[str, dict] = {}
        # user_id -> asyncio background task
        self.execution_tasks: Dict[str, asyncio.Task] = {}

    # ----------------------------------------------------------
    # SESSION INIT — Exchange request_token → access_token
    # ----------------------------------------------------------
    async def initialize_session(
        self, user_id: str, api_key: str, api_secret: str, request_token: str
    ) -> bool:
        """
        Exchange Zerodha request_token for a real access_token.
        Called once per day after user logs in via Zerodha OAuth.
        """
        if not KITE_AVAILABLE:
            logging.error("kiteconnect not installed. Cannot initialize real session.")
            return False
        try:
            loop = asyncio.get_running_loop()

            def _generate():
                kite = KiteConnect(api_key=api_key)
                session = kite.generate_session(request_token, api_secret=api_secret)
                kite.set_access_token(session["access_token"])
                return kite

            kite = await loop.run_in_executor(None, _generate)

            self.active_sessions[user_id] = kite
            self.live_pnls[user_id] = {
                "live_pnl": 0.0,
                "status": "active",
                "active_positions_count": 0,
                "positions": {}
            }
            logging.info(f"[ZERODHA] Real KiteConnect session initialized for user: {user_id}")
            return True

        except Exception as e:
            logging.error(f"[ZERODHA] Session init failed for {user_id}: {e}")
            return False

    # ----------------------------------------------------------
    # GET REAL LIVE P&L — from Zerodha positions API
    # ----------------------------------------------------------
    async def get_live_pnl(self, user_id: str) -> dict:
        """
        Fetch REAL live P&L from Zerodha positions API.
        Returns total unrealized + realized P&L for today.
        """
        kite = self.active_sessions.get(user_id)

        if kite:
            try:
                loop = asyncio.get_running_loop()

                def _fetch_positions():
                    return kite.positions()

                pos_data = await loop.run_in_executor(None, _fetch_positions)

                # Sum up today's net P&L across all positions
                net_positions = pos_data.get("net", [])
                total_pnl = sum(
                    p.get("unrealised", 0) + p.get("realised", 0)
                    for p in net_positions
                )
                open_count = sum(1 for p in net_positions if p.get("quantity", 0) != 0)

                # Update cache
                self.live_pnls[user_id] = {
                    "live_pnl": round(total_pnl, 2),
                    "status": "active",
                    "active_positions_count": open_count,
                    "positions": {p["tradingsymbol"]: p for p in net_positions}
                }

                logging.info(f"[ZERODHA] Live PnL for {user_id}: ₹{total_pnl:.2f} | {open_count} positions")

            except Exception as e:
                logging.error(f"[ZERODHA] Failed to fetch positions for {user_id}: {e}")

        cached = self.live_pnls.get(user_id, {
            "live_pnl": 0.0,
            "status": "inactive",
            "active_positions_count": 0
        })

        return {
            "user_id": user_id,
            "live_pnl": round(cached.get("live_pnl", 0.0), 2),
            "status": cached.get("status", "inactive"),
            "timestamp": datetime.now().isoformat(),
            "active_positions_count": cached.get("active_positions_count", 0)
        }

    # ----------------------------------------------------------
    # GET REAL POSITIONS — full position details
    # ----------------------------------------------------------
    async def get_positions(self, user_id: str) -> list:
        """Fetch real open positions from Zerodha."""
        kite = self.active_sessions.get(user_id)
        if not kite:
            return []
        try:
            loop = asyncio.get_running_loop()
            pos_data = await loop.run_in_executor(None, kite.positions)
            return pos_data.get("net", [])
        except Exception as e:
            logging.error(f"[ZERODHA] get_positions failed for {user_id}: {e}")
            return []

    # ----------------------------------------------------------
    # GET REAL MARGIN — available funds from Zerodha
    # ----------------------------------------------------------
    async def get_margin(self, user_id: str) -> dict:
        """Fetch real available margin/funds from Zerodha."""
        kite = self.active_sessions.get(user_id)
        if not kite:
            return {"available": 0.0, "used": 0.0}
        try:
            loop = asyncio.get_running_loop()

            def _fetch_margin():
                return kite.margins("equity")

            margin_data = await loop.run_in_executor(None, _fetch_margin)
            available = margin_data.get("available", {}).get("live_balance", 0.0)
            used = margin_data.get("utilised", {}).get("debits", 0.0)
            return {"available": round(available, 2), "used": round(used, 2)}
        except Exception as e:
            logging.error(f"[ZERODHA] get_margin failed for {user_id}: {e}")
            return {"available": 0.0, "used": 0.0}

    # ----------------------------------------------------------
    # GET ORDER HISTORY — today's orders from Zerodha
    # ----------------------------------------------------------
    async def get_orders(self, user_id: str) -> list:
        """Fetch today's real order history from Zerodha."""
        kite = self.active_sessions.get(user_id)
        if not kite:
            return []
        try:
            loop = asyncio.get_running_loop()
            orders = await loop.run_in_executor(None, kite.orders)
            return orders or []
        except Exception as e:
            logging.error(f"[ZERODHA] get_orders failed for {user_id}: {e}")
            return []

    # ----------------------------------------------------------
    # START STRATEGY — register and start background loop
    # ----------------------------------------------------------
    async def start_strategy(self, user_id: str, strategy_id: str, settings: dict):
        """Activates a strategy for a user and starts execution loop."""
        if user_id not in self.running_strategies:
            self.running_strategies[user_id] = {}

        self.running_strategies[user_id][strategy_id] = settings
        logging.info(f"[ENGINE] Strategy {strategy_id} deployed for {user_id}")

        # Start background P&L polling loop if not already running
        if user_id not in self.execution_tasks or self.execution_tasks[user_id].done():
            self.execution_tasks[user_id] = asyncio.create_task(
                self._live_pnl_polling_loop(user_id)
            )

    # ----------------------------------------------------------
    # STOP STRATEGY
    # ----------------------------------------------------------
    async def stop_strategy(self, user_id: str, strategy_id: str):
        """Stops a running strategy."""
        if user_id in self.running_strategies:
            self.running_strategies[user_id].pop(strategy_id, None)
            logging.info(f"[ENGINE] Strategy {strategy_id} stopped for {user_id}")

            # Cancel loop if no more strategies running
            if not self.running_strategies[user_id]:
                task = self.execution_tasks.get(user_id)
                if task and not task.done():
                    task.cancel()
                    logging.info(f"[ENGINE] Background loop cancelled for {user_id}")

    # ----------------------------------------------------------
    # UPDATE LIVE SETTINGS dynamically
    # ----------------------------------------------------------
    async def update_live_settings(self, user_id: str, strategy_id: str, settings: dict):
        """Dynamically apply new MTM limits or lot sizes to a running strategy."""
        if user_id in self.running_strategies and strategy_id in self.running_strategies[user_id]:
            self.running_strategies[user_id][strategy_id] = settings
            logging.info(f"[ENGINE] Settings updated live for {strategy_id} / {user_id}")

    # ----------------------------------------------------------
    # BACKGROUND P&L POLLING LOOP
    # Polls Zerodha every 3 seconds for real P&L updates
    # ----------------------------------------------------------
    async def _live_pnl_polling_loop(self, user_id: str):
        """
        Background task that polls Zerodha positions every 3 seconds.
        Updates self.live_pnls cache used by /user/live-pnl endpoint.
        """
        logging.info(f"[ENGINE] Live P&L polling started for user: {user_id}")
        try:
            while True:
                if not self.running_strategies.get(user_id):
                    break

                await self.get_live_pnl(user_id)

                # Check MTM limits for each active strategy
                cached = self.live_pnls.get(user_id, {})
                total_pnl = cached.get("live_pnl", 0.0)

                for strat_id, strat_settings in list(self.running_strategies.get(user_id, {}).items()):
                    if strat_settings.get("mtm_enabled"):
                        max_loss = strat_settings.get("mtm_max_loss", 5000)
                        max_profit = strat_settings.get("mtm_max_profit", 12000)

                        if total_pnl <= -max_loss:
                            logging.warning(
                                f"[MTM] Max loss -₹{max_loss} hit for {user_id}/{strat_id}! Stopping."
                            )
                            cached["status"] = "loss_hit"
                            await self.stop_strategy(user_id, strat_id)

                        elif total_pnl >= max_profit:
                            logging.info(
                                f"[MTM] Profit target +₹{max_profit} hit for {user_id}/{strat_id}! Stopping."
                            )
                            cached["status"] = "profit_hit"
                            await self.stop_strategy(user_id, strat_id)

                await asyncio.sleep(3)  # Poll every 3 seconds

        except asyncio.CancelledError:
            logging.info(f"[ENGINE] P&L polling loop cancelled for {user_id}")
        except Exception as e:
            logging.error(f"[ENGINE] Polling loop error for {user_id}: {e}")

    # ----------------------------------------------------------
    # CHECK IF SESSION IS ACTIVE
    # ----------------------------------------------------------
    def is_session_active(self, user_id: str) -> bool:
        return user_id in self.active_sessions


# Global trading engine instance (imported by api/brokers.py and api/strategies.py)
trading_engine = TradingEngine()
