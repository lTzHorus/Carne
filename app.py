from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

# Configure CORS
CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv('ALLOWED_ORIGINS', '*').split(','),
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

# MongoDB Connection with proper SSL handling
def get_mongo_client():
    MONGO_URI = os.getenv("MONGO_URI")
    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable not set")
    
    # For development/testing (less secure)
    if os.getenv('FLASK_ENV') == 'development':
        connection_params = {
            'retryWrites': 'true',
            'w': 'majority',
            'tls': 'true',
            'tlsAllowInvalidCertificates': 'true',
            'connectTimeoutMS': '30000',
            'socketTimeoutMS': '30000',
            'serverSelectionTimeoutMS': '30000'
        }
        params_str = '&'.join([f"{k}={v}" for k, v in connection_params.items()])
        return MongoClient(f"{MONGO_URI}?{params_str}")
    
    # For production (more secure)
    return MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=False,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        serverSelectionTimeoutMS=30000,
        retryWrites=True,
        w="majority"
    )

# Database connection
try:
    client = get_mongo_client()
    client.admin.command('ping')  # Test connection
    db = client.get_database(os.getenv('MONGO_DB_NAME', 'carne_astra'))
    print(f"Connected to MongoDB! Database: {db.name}")
except Exception as e:
    print(f"Error connecting to MongoDB: {str(e)}")
    db = None

# Helper functions
def validate_payment_data(data, partial_update=False):
    required_fields = ['description', 'value', 'dueDate', 'payer'] if not partial_update else []
    errors = {}
    
    for field in required_fields:
        if field not in data or not data[field]:
            errors[field] = "Required field"
    
    if 'value' in data and (not isinstance(data['value'], (int, float)) or data['value'] <= 0:
        errors['value'] = "Must be a positive number"
    
    if 'dueDate' in data:
        try:
            datetime.strptime(data['dueDate'], "%Y-%m-%d")
        except ValueError:
            errors['dueDate'] = "Invalid date format (use YYYY-MM-DD)"
    
    return errors if errors else None

# API Routes
@app.route('/api/payments', methods=['GET'])
def get_payments():
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        status_filter = request.args.get('status')
        query = {}
        
        if status_filter == 'paid':
            query['paid'] = True
        elif status_filter == 'pending':
            query['paid'] = False
            query['dueDate'] = {'$gte': datetime.now()}
        elif status_filter == 'overdue':
            query['paid'] = False
            query['dueDate'] = {'$lt': datetime.now()}
        
        payments = list(db.payments.find(query).sort("dueDate", 1))
        return dumps(payments)
    except Exception as e:
        app.logger.error(f"Error fetching payments: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/payments', methods=['POST'])
def add_payment():
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        if errors := validate_payment_data(data):
            return jsonify({"error": "Invalid data", "details": errors}), 400
        
        payment_data = {
            "description": data['description'],
            "value": float(data['value']),
            "dueDate": datetime.strptime(data['dueDate'], "%Y-%m-%d"),
            "payer": data['payer'],
            "paid": False,
            "paymentDate": None,
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }
        
        result = db.payments.insert_one(payment_data)
        return jsonify({
            "success": True,
            "id": str(result.inserted_id),
            "message": "Payment added successfully"
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"Error adding payment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/payments/<payment_id>/pay', methods=['PUT'])
def mark_as_paid(payment_id):
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        result = db.payments.update_one(
            {"_id": ObjectId(payment_id)},
            {
                "$set": {
                    "paid": True,
                    "paymentDate": datetime.now(),
                    "updatedAt": datetime.now()
                }
            }
        )
        
        if result.modified_count == 0:
            return jsonify({"error": "Payment not found or already paid"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment marked as paid"
        })
    except Exception as e:
        app.logger.error(f"Error marking payment as paid: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/payments/<payment_id>', methods=['PUT'])
def update_payment(payment_id):
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        if errors := validate_payment_data(data, partial_update=True):
            return jsonify({"error": "Invalid data", "details": errors}), 400
        
        update_data = {"$set": {"updatedAt": datetime.now()}}
        
        if 'description' in data:
            update_data['$set']['description'] = data['description']
        if 'value' in data:
            update_data['$set']['value'] = float(data['value'])
        if 'dueDate' in data:
            update_data['$set']['dueDate'] = datetime.strptime(data['dueDate'], "%Y-%m-%d")
        if 'payer' in data:
            update_data['$set']['payer'] = data['payer']
        
        result = db.payments.update_one(
            {"_id": ObjectId(payment_id)},
            update_data
        )
        
        if result.modified_count == 0:
            return jsonify({"error": "Payment not found or no changes made"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment updated successfully"
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"Error updating payment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/payments/<payment_id>', methods=['DELETE'])
def delete_payment(payment_id):
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        result = db.payments.delete_one({"_id": ObjectId(payment_id)})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Payment not found"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment deleted successfully"
        })
    except Exception as e:
        app.logger.error(f"Error deleting payment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# Frontend routes
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "database": "connected" if db else "disconnected"}), 200

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
