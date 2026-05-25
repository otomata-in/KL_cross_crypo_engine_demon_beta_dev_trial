"""
app/transport/serializer.py — State Serializer
================================================
Converts LiveState into a JSON-serializable payload for the frontend.
Extracted from ws_server.py.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any

from app.config import get_config
from app.engine.state import LiveState
from app.engine.spread import precompute_pair_fees, compute_spreads


def serialize_state(state: LiveState, current_threshold: float) -> Dict[str, Any]:
    """Convert LiveState into a payload for the frontend dashboard."""
    cfg = get_config()
    now_mono = time.monotonic()
    uptime = int(now_mono - state.started_at)
    
    # Needs a registry to know about exchanges
    from app.exchanges.registry import ExchangeRegistry
    registry = ExchangeRegistry()
    registry.load_from_config()
    exchange_pairs = registry.get_pairs()
    pair_fees = precompute_pair_fees()

    token_data = {}
    for token in state.tokens:
        exchanges_data = {}
        for ex in state.enabled_exchanges:
            ob = state.exchanges[ex].get(token, {})
            exchanges_data[ex] = {
                "bid": ob.get("bid"),
                "ask": ob.get("ask"),
                "bid_depth": round(ob.get("bid_depth", 0), 2),
                "ask_depth": round(ob.get("ask_depth", 0), 2),
                "age_ms": int((now_mono - ob["updated"]) * 1000) if ob.get("updated") else None,
                "status": state.ws_status[ex].get(token, "disconnected"),
            }

        spread_pairs = []
        for ex_a, ex_b in exchange_pairs:
            ob_a = state.exchanges[ex_a].get(token, {})
            ob_b = state.exchanges[ex_b].get(token, {})

            a_bid = ob_a.get("bid")
            a_ask = ob_a.get("ask")
            b_bid = ob_b.get("bid")
            b_ask = ob_b.get("ask")
            
            fees = pair_fees.get((ex_a, ex_b), 0.0)
            label_a = cfg.exchanges[ex_a].label
            label_b = cfg.exchanges[ex_b].label

            if all([a_bid, a_ask, b_bid, b_ask]):
                spread_a2b, spread_b2a = compute_spreads(
                    a_bid, a_ask, b_bid, b_ask, ex_a, ex_b, state.usdt_usdc_rate
                )
                
                net_a2b = spread_a2b - fees
                net_b2a = spread_b2a - fees

                spread_pairs.append({
                    "ex_buy": ex_a, "ex_sell": ex_b,
                    "label": f"{label_a}→{label_b}",
                    "gross": round(spread_a2b, 4), "net": round(net_a2b, 4),
                    "fees": round(fees, 4),
                })
                spread_pairs.append({
                    "ex_buy": ex_b, "ex_sell": ex_a,
                    "label": f"{label_b}→{label_a}",
                    "gross": round(spread_b2a, 4), "net": round(net_b2a, 4),
                    "fees": round(fees, 4),
                })
            else:
                spread_pairs.append({
                    "ex_buy": ex_a, "ex_sell": ex_b,
                    "label": f"{label_a}→{label_b}",
                    "gross": None, "net": None, "fees": round(fees, 4),
                })
                spread_pairs.append({
                    "ex_buy": ex_b, "ex_sell": ex_a,
                    "label": f"{label_b}→{label_a}",
                    "gross": None, "net": None, "fees": round(fees, 4),
                })

        valid_nets = [sp["net"] for sp in spread_pairs if sp["net"] is not None]
        best_net = max(valid_nets) if valid_nets else None
        best_pair_entry = None
        if best_net is not None:
            best_pair_entry = next((sp for sp in spread_pairs if sp["net"] == best_net), None)

        # Update session high
        if best_net is not None and best_net > state.spread_history[token]["max_net"]:
            state.spread_history[token]["max_net"] = best_net

        sh_net = state.spread_history[token]["max_net"]
        session_high_net = round(sh_net, 4) if sh_net > -999 else None

        token_category_map = cfg.get_token_category_map()
        
        token_data[token] = {
            "category": token_category_map.get(token, "Other"),
            "exchanges": exchanges_data,
            "spread_pairs": spread_pairs,
            "best_net": round(best_net, 4) if best_net is not None else None,
            "best_net_label": best_pair_entry["label"] if best_pair_entry else None,
            "best_gross": round(best_pair_entry["gross"], 4) if best_pair_entry and best_pair_entry["gross"] is not None else None,
            "best_fees": round(best_pair_entry["fees"], 4) if best_pair_entry else None,
            "session_high_net": session_high_net,
            "opp_count": state.opp_count.get(token, 0),
            "opp_best": round(state.opp_best.get(token, 0), 4) if token in state.opp_best else None,
            "opp_last": state.opp_last.get(token),
        }

    exchange_meta = {}
    for ex in state.enabled_exchanges:
        ex_cfg = cfg.exchanges[ex]
        connected = sum(1 for s in state.ws_status[ex].values() if s == "connected")
        total = len(state.supported_tokens.get(ex, []))
        exchange_meta[ex] = {
            "label": ex_cfg.label,
            "quote": ex_cfg.quote,
            "connected": connected,
            "total": total,
        }

    pair_fees_map = {}
    for (a, b), fee in pair_fees.items():
        key = f"{a}_{b}"
        if key not in pair_fees_map:
            pair_fees_map[key] = {
                "ex_a": a, "ex_b": b,
                "label": f"{cfg.exchanges[a].label}↔{cfg.exchanges[b].label}",
                "total": round(fee, 4),
            }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime,
        "threshold": current_threshold,
        "exchanges_list": state.enabled_exchanges,
        "exchange_meta": exchange_meta,
        "pair_fees": pair_fees_map,
        "total_tokens": len(state.tokens),
        "update_count": state.update_count.copy(),
        "usdt_usdc_rate": state.usdt_usdc_rate,
        "opp_total": state.opp_total,
        "categories": cfg.get_categories(),
        "tokens": state.tokens,
        "token_data": token_data,
    }
