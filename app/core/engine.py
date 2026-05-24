import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional

# Mock KiteConnect SDK - To illustrate real production Kite SDK interactions
class MockKiteConnect:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = None

    def generate_session(self, request_token: str, api_secret: str):
        self.access_token = "mock_access_token_" + request_token
        return {"access_token": self.access_token, "user_id": "VB_TRADER_101"}

    def ltp(self, instrument_token: str) -> Dict[str, Dict[str, float]]:
        base_prices = {"NSE:NIFTY 50": 22400.0, "NSE:NIFTY BANK": 48000.0}
        current_ltp = base_prices.get(instrument_token, 150.0)
        fluctuation = random.uniform(-5.0, 5.2)
        return {instrument_token: {"last_price": current_ltp + fluctuation}}

    def place_order(self, variety, exchange, tradingsymbol, transaction_type, quantity, product, order_type, price=None, trigger_price=None):
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
            loop = asyncio.get_running_loop()
            kite = MockKiteConnect(api_key, api_secret)
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
        
        if user_id not in self.execution_tasks or self.execution_tasks[user_id].done():
            self.execution_tasks[user_id] = asyncio.create_task(self._live_trading_loop(user_id))

    async def stop_strategy(self, user_id: str, strategy_id: str):
        """Halts a strategy and triggers emergency exits for any open positions belonging to it."""
        if user_id in self.running_strategies and strategy_id in self.running_strategies[user_id]:
            del self.running_strategies[user_id][strategy_id]
            logging.info(f"Strategy {strategy_id} stopped manually for user {user_id}")
            
            await self._emergency_square_off(user_id, strategy_id)
            
            if not self.running_strategies[user_id]:
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
        """Core Production Tick Engine running in background."""
        logging.info(f"Background trading loop successfully spawned for user: {user_id}")
        kite = self.active_sessions.get(user_id)
        
        if not kite:
            logging.error(f"Cannot run trading loop for {user_id}. Active broker session not found.")
            return

        try:
            while True:
                nifty_tick = kite.ltp("NSE:NIFTY 50")["NSE:NIFTY 50"]["last_price"]
                
                total_pnl = 0.0
                active_pos = 0
                user_state = self.live_pnls.get(user_id, {})
                
                for strat_id, settings in list(self.running_strategies.get(user_id, {}).items()):
                    if strat_id not in user_state.get("positions", {}):
                        mock_strike = int(round(nifty_tick / 50.0) * 50.0)
                        tradingsymbol = f"NIFTY{datetime.now().strftime('%y%m%d')}{mock_strike}CE"
                        
                        qty = settings["lot_size"] * 50
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
                    
                    pos = user_state["positions"][strat_id]
                    index_change = nifty_tick - 22400.0
                    pos["current_price"] = max(2.0, 120.0 + (index_change * 0.4) + random.uniform(-1.0, 1.2))
                    
                    pos_pnl = (pos["current_price"] - pos["entry_price"]) * pos["quantity"]
                    total_pnl += pos_pnl
                    active_pos += 1
                
                for strat_id, settings in list(self.running_strategies.get(user_id, {}).items()):
                    if settings.get("mtm_enabled"):
                        pos_info = user_state["positions"].get(strat_id)
                        if pos_info:
                            strat_pnl = (pos_info["current_price"] - pos_info["entry_price"]) * pos_info["quantity"]
                            
                            if strat_pnl <= -settings["mtm_max_loss"]:
                                logging.warning(f"[MTM EMERGENCY TRIGGERED] Daily Max Loss Limit (-₹{settings['mtm_max_loss']}) hit for {strat_id}!")
                                user_state["status"] = "loss_hit"
                                await self.stop_strategy(user_id, strat_id)
                                
                            elif strat_pnl >= settings["mtm_max_profit"]:
                                logging.info(f"[MTM TARGET ACHIEVED] Daily Max Profit Target (+₹{settings['mtm_max_profit']}) achieved for {strat_id}!")
                                user_state["status"] = "profit_hit"
                                await self.stop_strategy(user_id, strat_id)

                user_state["live_pnl"] = total_pnl
                user_state["active_positions_count"] = active_pos
                self.live_pnls[user_id].update(user_state)
                
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
            
            kite.place_order(
                variety="regular", exchange="NFO", tradingsymbol=pos["tradingsymbol"],
                transaction_type="SELL", quantity=pos["quantity"], product="MIS", order_type="MARKET"
            )
            
            del user_state["positions"][strategy_id]
            user_state["active_positions_count"] = len(user_state["positions"])
            
            if user_state["active_positions_count"] == 0:
                if user_state["status"] not in ["profit_hit", "loss_hit"]:
                    user_state["status"] = "inactive"

# Global trading engine instance
trading_engine = TradingEngine()
