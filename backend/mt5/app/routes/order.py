from flask import Blueprint, jsonify, request
import MetaTrader5 as mt5
import logging
from flasgger import swag_from

order_bp = Blueprint('order', __name__)
logger = logging.getLogger(__name__)

# Mapping from string representation to MT5 constants
ORDER_TYPE_MAPPING = {
    "BUY": mt5.ORDER_TYPE_BUY,
    "SELL": mt5.ORDER_TYPE_SELL,
    "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
    "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
    "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
    "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
    "BUY_STOP_LIMIT": mt5.ORDER_TYPE_BUY_STOP_LIMIT,
    "SELL_STOP_LIMIT": mt5.ORDER_TYPE_SELL_STOP_LIMIT,
}

FILLING_TYPE_MAPPING = {
    "ORDER_FILLING_FOK": mt5.ORDER_FILLING_FOK,
    "ORDER_FILLING_IOC": mt5.ORDER_FILLING_IOC,
    "ORDER_FILLING_RETURN": mt5.ORDER_FILLING_RETURN,
}

@order_bp.route('/order', methods=['POST'])
@swag_from({
    'tags': ['Order'],
    'summary': 'Send Market or Pending Order',
    'description': 'Execute any type of MT5 order. For pending orders (LIMIT, STOP), the `price` field is required. For STOP_LIMIT orders, `price` and `stoplimit` are required.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string', 'description': 'The financial instrument to trade.'},
                    'volume': {'type': 'number', 'description': 'The volume of the order.'},
                    'type': {
                        'type': 'string',
                        'description': 'The type of the order.',
                        'enum': list(ORDER_TYPE_MAPPING.keys())
                    },
                    'price': {'type': 'number', 'description': 'Required for all pending orders.'},
                    'stoplimit': {'type': 'number', 'description': 'Required for BUY_STOP_LIMIT and SELL_STOP_LIMIT orders.'},
                    'sl': {'type': 'number', 'description': 'Stop Loss price.'},
                    'tp': {'type': 'number', 'description': 'Take Profit price.'},
                    'deviation': {'type': 'integer', 'default': 20, 'description': 'Price deviation for market orders.'},
                    'magic': {'type': 'integer', 'default': 0, 'description': 'Magic number for the order.'},
                    'comment': {'type': 'string', 'default': '', 'description': 'Order comment.'},
                    'type_filling': {
                        'type': 'string',
                        'description': 'Order filling type.',
                        'enum': list(FILLING_TYPE_MAPPING.keys()),
                        'default': 'ORDER_FILLING_IOC'
                    }
                },
                'required': ['symbol', 'volume', 'type']
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Order executed successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'result': {'type': 'object'}
                }
            }
        },
        400: {
            'description': 'Bad request, missing parameters, or order failed.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})
def send_order_endpoint():
    """
    Handles sending all types of MT5 orders.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # --- Validate required fields ---
        required_fields = ['symbol', 'volume', 'type']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields: symbol, volume, type"}), 400

        order_type_mt5 = data.get('type')
        if order_type_mt5 is None:
            return jsonify({"error": f"Invalid order type: {order_type_mt5}"}), 400

        # --- Prepare the base order request ---
        request_data = {
            "symbol": data['symbol'],
            "volume": float(data['volume']),
            "type": order_type_mt5,
            "deviation": data.get('deviation', 20),
            "magic": data.get('magic', 0),
            "comment": data.get('comment', ''),
            "type_time": mt5.ORDER_TIME_GTC, # Good Till Canceled
            "type_filling": FILLING_TYPE_MAPPING.get(data.get('type_filling'), mt5.ORDER_FILLING_IOC),
        }

        # --- Set action and price based on order type ---
        is_market_order = order_type_mt5 in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]
        is_stop_limit_order = order_type_mt5 in [mt5.ORDER_TYPE_BUY_STOP_LIMIT, mt5.ORDER_TYPE_SELL_STOP_LIMIT]

        if is_market_order:
            request_data["action"] = mt5.TRADE_ACTION_DEAL
            tick = mt5.symbol_info_tick(data['symbol'])
            if tick is None:
                return jsonify({"error": "Failed to get symbol price"}), 400
            request_data["price"] = tick.ask if order_type_mt5 == mt5.ORDER_TYPE_BUY else tick.bid
        else: # Pending order
            request_data["action"] = mt5.TRADE_ACTION_PENDING
            if 'price' not in data:
                return jsonify({"error": "The 'price' field is required for pending orders"}), 400
            request_data["price"] = float(data['price'])
            
            if is_stop_limit_order:
                if 'stoplimit' not in data:
                    return jsonify({"error": "The 'stoplimit' field is required for STOP_LIMIT orders"}), 400
                request_data["price_stoplimit"] = float(data['stoplimit'])


        # --- Add optional SL/TP if provided ---
        if 'sl' in data and data['sl'] is not None:
            request_data["sl"] = float(data['sl'])
        if 'tp' in data and data['tp'] is not None:
            request_data["tp"] = float(data['tp'])

        # --- Send the order to MetaTrader 5 ---
        result = mt5.order_send(request_data)
        
        if result is None:
            error_code, error_str = mt5.last_error()
            logger.error(f"Order send failed. Last error: code {error_code}, message: {error_str}")
            return jsonify({
                "error": "Order send failed. MT5 returned no result.",
                "mt5_error_code": error_code,
                "mt5_error_message": error_str
            }), 400

        result_dict = result._asdict()
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(f"Order not successful: {result.comment}. Result: {result_dict}")
            return jsonify({
                "error": f"Order failed: {result.comment}",
                "result": result_dict
            }), 400

        logger.info(f"Order executed successfully: {result_dict}")
        return jsonify({
            "message": "Order executed successfully",
            "result": result_dict
        })

    except Exception as e:
        logger.error(f"An exception occurred in send_order_endpoint: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
