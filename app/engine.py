import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional

# Mock KiteConnect SDK - To illustrate real production Kite SDK interactions
# In real production: from kiteconnect import KiteConnect
class MockKiteConnect:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = None

    def generate_session(self, request_token: str, api_secret: str):
        # Authenticates session via broker callback redirect
        self.access_token = "mock_access_token_" + request_token
        return {"access_token": self.access_token, "user_id": "VB_TRADER_101"}

    def ltp(self, instrument_token: str) -> Dict[str, Dict[str, float]]:
        # Returns Last Traded Price for instruments
        base_prices = {"NSE:NIFTY 50": 22400.0, "NSE:NIFTY BANK": 48000.0}
        current_ltp = base_prices.get(instrument_token, 150.0)
        # Add random tick fluctuation to simulate live market movements
        fluctuation = random.uniform(-5.0, 5.2)
        return {instrument_token: {"last_price": current_ltp + fluctuation}}

    def place_order(self, variety, exchange, tradingsymbol, transaction_type, quantity, product, order_type, price=None, trigger_price=None):
        # Simulated order placement
        order_id = "ORD_" + str(random.randint(100000, 999999))
        logging.info(f"[ORDER PLACED] ID: {order_id} | {transaction_type} {quantity} qty of {tradingsymbol} ({exchange}) via {product}")
        return order_id

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class TradingEngine:
    def __init__(self):
        self.active_sessions: Dict[str, MockKiteConnect] = {}  # user_id -> Kite instance
        self.running_strategies: Dict[str, Dict[str, dict]] = {}  # user_id -> {strategy_id -> settings}
        self.live_pnls: Dict[str, dict] = {}  # user_id -> {live_pnl, status, positions}
        self.execution_tasks: Dict[str, asyncio.Task] = {}  # user_id -> asyncio Task

    async def initialize_session(self, user_id: str, api_key: str, api_secret: str, request_token: str) -> bool:
        """Exchanges request token for active Kite API Session."""
        try:
            # Wrap synchronous SDK block in asyncio-safe run_in_executor
            loop = asyncio.get_running_loop()
            kite = MockKiteConnect(api_key, api_secret)
            
            # Simulated network latency of API exchange
            session = await loop.run_in_executor(None, kite.generate_session, request_token, api_secret)
            
            self.active_sessions[user_id] = kite
            self.live_pnls[user_id] = {
                "live_pnl": 0.0,
                "status": "active",
                "active_positions_count": 0,
                "positions": {}
            }
            logging.info(f"Successfully initialized Kite Session for user {user_id}")
            return True
        except Exception as e:
            logging.error(f"Error during Kite Connect authorization handshake: {e}")
            return False

    async def start_strategy(self, user_id: str, strategy_id: str, settings: dict):
        """Starts a strategy loop for a user."""
        if user_id not in self.running_strategies:
            self.running_strategies[user_id] = {}
        
        self.running_strategies[user_id][strategy_id] = settings
        logging.info(f"Strategy {strategy_id} deployed for user {user_id}. Running risk limits: {settings}")
        
        # Start the background task loop if it's not already running
        if user_id not in self.execution_tasks or self.execution_tasks[user_id].done():
            self.execution_tasks[user_id] = asyncio.create_task(self._live_trading_loop(user_id))

    async def stop_strategy(self, user_id: str, strategy_id: str):
        """Halts a strategy and triggers emergency exits for any open positions belonging to it."""
        if user_id in self.running_strategies and strategy_id in self.running_strategies[user_id]:
            del self.running_strategies[user_id][strategy_id]
            logging.info(f"Strategy {strategy_id} stopped manually for user {user_id}")
            
            # Emergency position square-off
            await self._emergency_square_off(user_id, strategy_id)
            
            if not self.running_strategies[user_id]:
                # If no more active strategies, cancel the main trading task loop
                if user_id in self.execution_tasks:
                    self.execution_tasks[user_id].cancel()
                    logging.info(f"Cancelled background execution loop for user {user_id}")

    async def update_live_settings(self, user_id: str, strategy_id: str, settings: dict):
        """Dynamically applies new MTM limits or lot sizing to active strategies."""
        if user_id in self.running_strategies and strategy_id in self.running_strategies[user_id]:
            self.running_strategies[user_id][strategy_id] = settings
            logging.info(f"Dynamic setting override applied to active strategy {strategy_id} for user {user_id}")

    async def get_live_pnl(self, user_id: str) -> dict:
        """Returns the cached PnL and active status for dashboard API consumption."""
        user_pnl = self.live_pnls.get(user_id, {
            "live_pnl": 0.0,
            "status": "inactive",
            "active_positions_count": 0
        })
        return {
            "user_id": user_id,
            "live_pnl": round(user_pnl["live_pnl"], 2),
            "status": user_pnl["status"],
            "timestamp": datetime.now().isoformat(),
            "active_positions_count": user_pnl["active_positions_count"]
        }

    async def _live_trading_loop(self, user_id: str):
        """
        The Core Production Tick Engine.
        Runs continuously in the background to:
        1. Fetch Live Option Ticks.
        2. Evaluate signal triggers.
        3. Place orders.
        4. Track live positions & P&L.
        5. Enforce Mark-to-Market (MTM) Guard emergency triggers.
        """
        logging.info(f"Background trading loop successfully spawned for user: {user_id}")
        kite = self.active_sessions.get(user_id)
        
        if not kite:
            logging.error(f"Cannot run trading loop for {user_id}. Active broker session not found.")
            return

        try:
            while True:
                # 1. Fetch Ticks (Example: Fetching Nifty & BankNifty spot prices)
                # In real production: use KiteTicker WebSocket client, or parallel multi-threading
                nifty_tick = kite.ltp("NSE:NIFTY 50")["NSE:NIFTY 50"]["last_price"]
                
                # 2. Update simulated positions & P&L based on active strategies
                total_pnl = 0.0
                active_pos = 0
                user_state = self.live_pnls.get(user_id, {})
                
                for strat_id, settings in list(self.running_strategies.get(user_id, {}).items()):
                    # Simulate having an open position in an option contract
                    # In real production, query self.active_sessions[user_id].positions()
                    if strat_id not in user_state.get("positions", {}):
                        # Enter a mock trade for demonstration (Buy 1 Nifty Call option)
                        mock_strike = int(round(nifty_tick / 50.0) * 50.0)
                        tradingsymbol = f"NIFTY{datetime.now().strftime('%y%m%d')}{mock_strike}CE"
                        
                        # Place order on exchange
                        qty = settings["lot_size"] * 50  # Nifty lot size is 50
                        order_id = kite.place_order(
                            variety="regular", exchange="NFO", tradingsymbol=tradingsymbol,
                            transaction_type="BUY", quantity=qty, product="MIS", order_type="MARKET"
                        )
                        
                        user_state["positions"][strat_id] = {
                            "tradingsymbol": tradingsymbol,
                            "entry_price": 120.0,
                            "current_price": 120.0,
                            "quantity": qty,
                            "order_id": order_id
                        }
                    
                    # Update option premium dynamically based on index ticks
                    pos = user_state["positions"][strat_id]
                    index_change = nifty_tick - 22400.0  # reference base index
                    pos["current_price"] = max(2.0, 120.0 + (index_change * 0.4) + random.uniform(-1.0, 1.2))  # Delta ≈ 0.4
                    
                    # Calculate open trade P&L: (Current Price - Entry Price) * Quantity
                    pos_pnl = (pos["current_price"] - pos["entry_price"]) * pos["quantity"]
                    total_pnl += pos_pnl
                    active_pos += 1
                
                # 3. Check MTM Daily Guards across active strategies
                # Enforce emergency stops if MTM enabled
                for strat_id, settings in list(self.running_strategies.get(user_id, {}).items()):
                    if settings.get("mtm_enabled"):
                        pos_info = user_state["positions"].get(strat_id)
                        if pos_info:
                            strat_pnl = (pos_info["current_price"] - pos_info["entry_price"]) * pos_info["quantity"]
                            
                            # 3a. Max Loss Check (Target hit)
                            if strat_pnl <= -settings["mtm_max_loss"]:
                                logging.warning(f"[MTM EMERGENCY TRIGGERED] Daily Max Loss Limit (-₹{settings['mtm_max_loss']}) hit for {strat_id}!")
                                user_state["status"] = "loss_hit"
                                await self.stop_strategy(user_id, strat_id)
                                
                            # 3b. Max Profit Check (Target hit)
                            elif strat_pnl >= settings["mtm_max_profit"]:
                                logging.info(f"[MTM TARGET ACHIEVED] Daily Max Profit Target (+₹{settings['mtm_max_profit']}) achieved for {strat_id}!")
                                user_state["status"] = "profit_hit"
                                await self.stop_strategy(user_id, strat_id)

                # Update live states
                user_state["live_pnl"] = total_pnl
                user_state["active_positions_count"] = active_pos
                self.live_pnls[user_id].update(user_state)
                
                # Dynamic polling tick speed (Simulates 1-second background thread ticking)
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            logging.info(f"Trading loop gracefully shutdown for user {user_id}")
        except Exception as e:
            logging.error(f"Error in backend live-trading execution task loop: {e}")

    async def _emergency_square_off(self, user_id: str, strategy_id: str):
        """Places emergency sell order to secure remaining premium and close active broker positions."""
        kite = self.active_sessions.get(user_id)
        user_state = self.live_pnls.get(user_id)
        
        if not kite or not user_state:
            return

        pos = user_state["positions"].get(strategy_id)
        if pos:
            logging.info(f"[EMERGENCY CLEARANCE] Placing square-off sell order for {pos['quantity']} qty of {pos['tradingsymbol']}")
            
            # Place reversing order to sell active options holdings
            kite.place_order(
                variety="regular", exchange="NFO", tradingsymbol=pos["tradingsymbol"],
                transaction_type="SELL", quantity=pos["quantity"], product="MIS", order_type="MARKET"
            )
            
            # Purge positions
            del user_state["positions"][strategy_id]
            user_state["active_positions_count"] = len(user_state["positions"])
            
            # If all cleared, reset status or keep hit flag
            if user_state["active_positions_count"] == 0:
                if user_state["status"] not in ["profit_hit", "loss_hit"]:
                    user_state["status"] = "inactive"

# Global trading engine instance
trading_engine = TradingEngine()
