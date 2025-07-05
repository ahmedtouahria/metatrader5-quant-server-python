import logging
import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import MetaTrader5 as mt5
from flasgger import Swagger
from werkzeug.middleware.proxy_fix import ProxyFix
from swagger import swagger_config

# Import routes
from routes.health import health_bp
from routes.symbol import symbol_bp
from routes.data import data_bp
from routes.position import position_bp
from routes.order import order_bp
from routes.history import history_bp
from routes.error import error_bp
from routes.account import account_bp

load_dotenv()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'

swagger = Swagger(app, config=swagger_config)
@app.before_request
def require_token_globally():
    # Allow these public routes (e.g. health check, Swagger UI, favicon, etc.)
    public_paths = [
        '/health',
        '/apidocs',           # Swagger UI
        '/apidocs/',          # Swagger root
        '/flasgger_static/',            # Swagger assets
        '/favicon.ico',
        '/apispec_1.json'
    ]

    # Skip check for allowed paths
    if any(request.path.startswith(path) for path in public_paths):
        return

    auth_header = request.headers.get('Authorization', '')
    token = os.getenv('MT5_API_TOKEN')

    if not auth_header.startswith('Bearer ') or auth_header.split(' ')[1] != token:
        return jsonify({'error': 'Unauthorized'}), 401

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(symbol_bp)
app.register_blueprint(data_bp)
app.register_blueprint(position_bp)
app.register_blueprint(order_bp)
app.register_blueprint(history_bp)
app.register_blueprint(error_bp)
app.register_blueprint(account_bp)


app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

if __name__ == '__main__':
    if not mt5.initialize():
        logger.error("Failed to initialize MT5.")
    app.run(host='0.0.0.0', port=int(os.environ.get('MT5_API_PORT')))