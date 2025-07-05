from flask import Blueprint, jsonify, request
import MetaTrader5 as mt5
import logging
from lib import close_position, close_all_positions, get_positions
from flasgger import swag_from
from concurrent.futures import ThreadPoolExecutor, as_completed

position_bp = Blueprint('position', __name__)
logger = logging.getLogger(__name__)

@position_bp.route('/close_position', methods=['POST'])
@swag_from({
    'tags': ['Position'],
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'position': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'integer'},
                            'ticket': {'type': 'integer'},
                            'symbol': {'type': 'string'},
                            'volume': {'type': 'number'}
                        },
                        'required': ['type', 'ticket', 'symbol', 'volume']
                    }
                },
                'required': ['position']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Position closed successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'result': {
                        'type': 'object',
                        'properties': {
                            'retcode': {'type': 'integer'},
                            'order': {'type': 'integer'},
                            'magic': {'type': 'integer'},
                            'price': {'type': 'number'},
                            'symbol': {'type': 'string'},
                            # Add other relevant fields as needed
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Bad request or failed to close position.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def close_position_endpoint():
    """
    Close a Specific Position
    ---
    description: Close a specific trading position based on the provided position data.
    """
    try:
        data = request.get_json()
        if not data or 'position' not in data:
            return jsonify({"error": "Position data is required"}), 400
        
        result = close_position(data['position'])
        if result is None:
            return jsonify({"error": "Failed to close position"}), 400
        
        return jsonify({"message": "Position closed successfully", "result": result._asdict()})
    
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@position_bp.route('/close_all_positions', methods=['POST'])
@swag_from({
    'tags': ['Position'],
    'parameters': [
        {
            'name': 'magic',
            'in': 'query',
            'type': 'integer',
            'required': False,
            'description': 'Magic number to filter positions.'
        }
    ],
    'responses': {
        200: {
            'description': 'All positions closed successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'closed': {
                        'type': 'array',
                        'items': {'type': 'integer'}
                    },
                    'failed': {
                        'type': 'array',
                        'items': {'type': 'object'}
                    }
                }
            }
        },
        400: {
            'description': 'Bad request or failed to close positions.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def close_all_positions_endpoint():
    """
    Close all open positions rapidly (concurrently)
    ---
    description: Closes all open positions for the current account using multithreading, optionally filtered by magic number.
    """
    try:
        if not mt5.initialize():
            return jsonify({'error': f'MT5 initialize failed: {mt5.last_error()}'}), 500

        positions = mt5.positions_get()
        if positions is None:
            mt5.shutdown()
            return jsonify({'error': f'positions_get failed: {mt5.last_error()}'}), 500

        closed = []
        failed = []

        def close_position(pos):
            try:
                order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(pos.symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask

                order_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": order_type,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": 10,
                    "magic": pos.magic,
                    "comment": "Closed by API",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC
                }

                result = mt5.order_send(order_request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"status": "closed", "ticket": pos.ticket}
                else:
                    return {"status": "failed", "ticket": pos.ticket, "symbol": pos.symbol, "error": result.retcode}
            except Exception as e:
                return {"status": "failed", "ticket": pos.ticket, "error": str(e)}

        # Run all in parallel
        with ThreadPoolExecutor(max_workers=len(positions)) as executor:
            futures = [executor.submit(close_position, pos) for pos in positions]

            for future in as_completed(futures):
                result = future.result()
                if result["status"] == "closed":
                    closed.append(result["ticket"])
                else:
                    failed.append(result)

        mt5.shutdown()
        return jsonify({"closed": closed, "failed": failed}), 200

    except Exception as e:
        logger.error(f"Error in close_all_positions: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
@position_bp.route('/modify_sl_tp', methods=['POST'])
@swag_from({
    'tags': ['Position'],
    'summary': 'Modify Stop Loss and Take Profit',
    'description': 'Modify the Stop Loss (SL) and Take Profit (TP) levels for a specific open position. Set sl or tp to 0.0 to remove it.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'position': {'type': 'integer', 'description': 'The ticket number of the position to modify.'},
                    'sl': {'type': 'number', 'description': 'The new Stop Loss price. Use 0 to remove.'},
                    'tp': {'type': 'number', 'description': 'The new Take Profit price. Use 0 to remove.'}
                },
                'required': ['position']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'SL/TP modified successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'result': {'type': 'object'}
                }
            }
        },
        400: {
            'description': 'Bad request or failed to modify SL/TP.'
        },
        404: {
            'description': 'Position not found.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def modify_sl_tp_endpoint():
    """
    Modify the Stop Loss (SL) and Take Profit (TP) levels for a specific position.
    """
    try:
        data = request.get_json()
        if not data or 'position' not in data:
            return jsonify({"error": "The 'position' ticket number is required"}), 400
        
        position_ticket = int(data['position'])
        
        # --- Robustly handle SL/TP values ---
        # MT5 expects float values. A value of 0.0 indicates no SL or TP.
        # We handle cases where sl/tp might be missing or None in the request.
        sl_price = float(data.get('sl', 0.0) or 0.0)
        tp_price = float(data.get('tp', 0.0) or 0.0)

        # --- Get position info to verify it exists and get the symbol ---
        # This makes the request more robust and explicit.
        position_info_tuple = mt5.positions_get(ticket=position_ticket)
        if not position_info_tuple:
            return jsonify({"error": f"Position with ticket {position_ticket} not found."}), 404
        
        position_info = position_info_tuple[0]

        # --- Prepare the request for MT5 ---
        request_data = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position_ticket,
            "symbol": position_info.symbol, # Including the symbol is best practice
            "sl": sl_price,
            "tp": tp_price
        }
        
        # --- Send the modification request ---
        result = mt5.order_send(request_data)
        
        if result is None:
            error_code, error_str = mt5.last_error()
            logger.error(f"Failed to modify SL/TP for position {position_ticket}. Last error: code {error_code}, message: {error_str}")
            return jsonify({
                "error": "Failed to modify SL/TP. MT5 returned no result.",
                "mt5_error_code": error_code,
                "mt5_error_message": error_str
            }), 400

        result_dict = result._asdict()
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(f"Modification of SL/TP for position {position_ticket} not successful: {result.comment}. Result: {result_dict}")
            return jsonify({
                "error": f"Failed to modify SL/TP: {result.comment}",
                "result": result_dict
            }), 400
        
        logger.info(f"SL/TP for position {position_ticket} modified successfully. Result: {result_dict}")
        return jsonify({"message": "SL/TP modified successfully", "result": result_dict})
    
    except Exception as e:
        logger.error(f"An exception occurred in modify_sl_tp_endpoint: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@position_bp.route('/get_positions', methods=['GET'])
@swag_from({
    'tags': ['Position'],
    'parameters': [
        {
            'name': 'magic',
            'in': 'query',
            'type': 'integer',
            'required': False,
            'description': 'Magic number to filter positions.'
        }
    ],
    'responses': {
        200: {
            'description': 'Positions retrieved successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'positions': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'ticket': {'type': 'integer'},
                                'time': {'type': 'string', 'format': 'date-time'},
                                'type': {'type': 'integer'},
                                'magic': {'type': 'integer'},
                                'symbol': {'type': 'string'},
                                'volume': {'type': 'number'},
                                'price_open': {'type': 'number'},
                                'sl': {'type': 'number'},
                                'tp': {'type': 'number'},
                                'price_current': {'type': 'number'},
                                'swap': {'type': 'number'},
                                'profit': {'type': 'number'},
                                'comment': {'type': 'string'},
                                'external_id': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Bad request or failed to retrieve positions.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def get_positions_endpoint():
    """
    Get Open Positions
    ---
    description: Retrieve all open trading positions, optionally filtered by magic number.
    """
    try:
        magic = request.args.get('magic', type=int)

        positions_df = get_positions(magic)

        if positions_df is None:
            return jsonify({"error": "Failed to retrieve positions"}), 500
            
        if positions_df.empty:
            return jsonify({"positions": []}), 200
            
        return jsonify(positions_df.to_dict(orient='records')), 200
    
    except Exception as e:
        logger.error(f"Error in get_positions: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@position_bp.route('/positions_total', methods=['GET'])
@swag_from({
    'tags': ['Position'],
    'responses': {
        200: {
            'description': 'Total number of open positions retrieved successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'total': {'type': 'integer'}
                }
            }
        },
        400: {
            'description': 'Failed to get positions total.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def positions_total_endpoint():
    """
    Get Total Open Positions
    ---
    description: Retrieve the total number of open trading positions.
    """
    try:
        total = mt5.positions_total()
        if total is None:
            return jsonify({"error": "Failed to get positions total"}), 400
        
        return jsonify({"total": total})
    
    except Exception as e:
        logger.error(f"Error in positions_total: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    




@position_bp.route('/close_positions_batch', methods=['POST'])
@swag_from({
    'tags': ['Position'],
    'summary': 'Close Multiple Positions (Batch)',
    'description': 'Closes a list of specific trading positions identified by their ticket numbers.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'tickets': {
                        'type': 'array',
                        'items': {'type': 'integer'},
                        'description': 'A list of position ticket numbers to close.'
                    }
                },
                'required': ['tickets']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Batch close operation completed. Check the response body for detailed results.',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'successful_closes': {
                        'type': 'array',
                        'items': {'type': 'object'}
                    },
                    'failed_closes': {
                        'type': 'array',
                        'items': {'type': 'object'}
                    }
                }
            }
        },
        400: {
            'description': 'Bad request, for example, missing the list of tickets.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def close_positions_batch_endpoint():
    """
    Closes multiple positions in a single batch request.
    """
    try:
        data = request.get_json()
        if not data or 'tickets' not in data or not isinstance(data['tickets'], list):
            return jsonify({"error": "A JSON array of 'tickets' is required."}), 400

        tickets_to_close = data['tickets']
        successful_closes = []
        failed_closes = []

        for ticket in tickets_to_close:
            # --- Get position details ---
            position_info_tuple = mt5.positions_get(ticket=ticket)
            if not position_info_tuple:
                failed_closes.append({"ticket": ticket, "error": "Position not found."})
                logger.warning(f"Attempted to close non-existent position with ticket: {ticket}")
                continue
            
            position_info = position_info_tuple[0]

            # --- Determine the correct closing order type ---
            order_type = mt5.ORDER_TYPE_SELL if position_info.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

            # --- Get the current price for closing ---
            tick = mt5.symbol_info_tick(position_info.symbol)
            if tick is None:
                failed_closes.append({"ticket": ticket, "error": f"Failed to get price for symbol {position_info.symbol}"})
                logger.error(f"Could not retrieve tick for {position_info.symbol} to close ticket {ticket}")
                continue

            price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask

            # --- Prepare the closing request ---
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": position_info.ticket,
                "symbol": position_info.symbol,
                "volume": position_info.volume,
                "type": order_type,
                "price": price,
                "deviation": 20,
                "magic": 0,
                "comment": "Batch Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }

            # --- Send the closing order ---
            result = mt5.order_send(close_request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                successful_closes.append({"ticket": ticket, "result": result._asdict()})
                logger.info(f"Successfully closed position {ticket} in batch operation.")
            else:
                error_message = result.comment if result else "order_send returned None"
                failed_closes.append({"ticket": ticket, "error": error_message, "result": result._asdict() if result else None})
                logger.error(f"Failed to close position {ticket} in batch. Reason: {error_message}")

        return jsonify({
            "message": "Batch close operation completed.",
            "successful_closes": successful_closes,
            "failed_closes": failed_closes
        })

    except Exception as e:
        logger.error(f"An exception occurred in close_positions_batch_endpoint: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
