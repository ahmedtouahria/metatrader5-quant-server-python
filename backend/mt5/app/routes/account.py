from flask import Blueprint, jsonify
import MetaTrader5 as mt5
import logging
from flasgger import swag_from

# Create a new blueprint for account-related endpoints
account_bp = Blueprint('account', __name__)
logger = logging.getLogger(__name__)

@account_bp.route('/account_info', methods=['GET'])
@swag_from({
    'tags': ['Account'],
    'summary': 'Get Account Information',
    'description': 'Retrieves detailed information about the connected MetaTrader 5 trading account.',
    'responses': {
        200: {
            'description': 'Account information retrieved successfully.',
            'schema': {
                'type': 'object',
                'properties': {
                    'login': {'type': 'integer'},
                    'trade_mode': {'type': 'integer'},
                    'leverage': {'type': 'integer'},
                    'limit_orders': {'type': 'integer'},
                    'margin_so_mode': {'type': 'integer'},
                    'trade_allowed': {'type': 'boolean'},
                    'trade_expert': {'type': 'boolean'},
                    'margin_mode': {'type': 'integer'},
                    'balance': {'type': 'number'},
                    'credit': {'type': 'number'},
                    'profit': {'type': 'number'},
                    'equity': {'type': 'number'},
                    'margin': {'type': 'number'},
                    'margin_free': {'type': 'number'},
                    'margin_level': {'type': 'number'},
                    'margin_so_call': {'type': 'number'},
                    'margin_so_so': {'type': 'number'},
                    'margin_initial': {'type': 'number'},
                    'margin_maintenance': {'type': 'number'},
                    'assets': {'type': 'number'},
                    'liabilities': {'type': 'number'},
                    'commission_blocked': {'type': 'number'},
                    'name': {'type': 'string'},
                    'server': {'type': 'string'},
                    'currency': {'type': 'string'},
                    'company': {'type': 'string'}
                }
            }
        },
        404: {
            'description': 'Failed to retrieve account information.'
        },
        500: {
            'description': 'Internal server error.'
        }
    }
})

def get_account_info_endpoint():
    """
    Retrieves and returns the MT5 account information.
    """
    try:
        # Request account info from MetaTrader 5
        account_info = mt5.account_info()
        
        if account_info is None:
            error_code, error_str = mt5.last_error()
            logger.error(f"Failed to get account info. Last error: code {error_code}, message: {error_str}")
            return jsonify({
                "error": "Failed to get account info from MT5.",
                "mt5_error_code": error_code,
                "mt5_error_message": error_str
            }), 404

        # Convert the named tuple to a dictionary for JSON serialization
        account_info_dict = account_info._asdict()
        
        logger.info(f"Successfully retrieved account info for login {account_info.login}.")
        return jsonify(account_info_dict)

    except Exception as e:
        logger.error(f"An exception occurred in get_account_info_endpoint: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
