from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from datetime import datetime
import os
import ssl

app = Flask(__name__, static_folder='.', static_url_path='')

# Configuração do CORS para permitir acesso mobile
CORS(app)

# Configuração segura da conexão com MongoDB Atlas
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://leoimarques:nT8QO2rCaps1RzwL@cluster0.ji1shyl.mongodb.net/carne_astra?retryWrites=true&w=majority")

def get_mongo_client():
    if not MONGO_URI:
        raise ValueError("Variável MONGO_URI não configurada")
    
    # Configuração de SSL customizada para o Render
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connection_params = {
        'ssl': True,
        'ssl_cert_reqs': ssl.CERT_NONE,
        'ssl_ca_certs': None,
        'retryWrites': True,
        'w': 'majority',
        'connectTimeoutMS': 30000,
        'socketTimeoutMS': 30000,
        'serverSelectionTimeoutMS': 30000,
        'tlsAllowInvalidCertificates': True
    }
    
    return MongoClient(MONGO_URI, **connection_params)

try:
    client = get_mongo_client()
    # Teste de conexão simplificado
    client.admin.command('ismaster')
    db = client.get_database('carne_astra')
    print(f"Conectado ao MongoDB! Banco: {db.name}")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {str(e)}")
    db = None

# Funções auxiliares
def validate_payment_data(data, partial_update=False):
    required_fields = ['description', 'value', 'dueDate', 'payer'] if not partial_update else []
    errors = {}
    
    for field in required_fields:
        if field not in data or not data[field]:
            errors[field] = "Campo obrigatório"
    
    if 'value' in data and (not isinstance(data['value'], (int, float)) or data['value'] <= 0:
        errors['value'] = "Valor deve ser um número positivo"
    
    if 'dueDate' in data:
        try:
            datetime.strptime(data['dueDate'], "%Y-%m-%d")
        except ValueError:
            errors['dueDate'] = "Formato de data inválido (use YYYY-MM-DD)"
    
    return errors if errors else None

# Rotas da API
@app.route('/api/payments', methods=['GET'])
def get_payments():
    if not db:
        return jsonify({"error": "Conexão com o banco de dados falhou"}), 500
    
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
        app.logger.error(f"Erro ao buscar pagamentos: {str(e)}")
        return jsonify({"error": "Erro interno ao processar a requisição"}), 500

@app.route('/api/payments', methods=['POST'])
def add_payment():
    if not db:
        return jsonify({"error": "Conexão com o banco de dados falhou"}), 500
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dados não fornecidos"}), 400
        
        if errors := validate_payment_data(data):
            return jsonify({"error": "Dados inválidos", "details": errors}), 400
        
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
            "message": "Parcela adicionada com sucesso"
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"Erro ao adicionar parcela: {str(e)}")
        return jsonify({"error": "Erro interno ao processar a requisição"}), 500

@app.route('/api/payments/<payment_id>/pay', methods=['PUT'])
def mark_as_paid(payment_id):
    if not db:
        return jsonify({"error": "Conexão com o banco de dados falhou"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "ID de parcela inválido"}), 400
            
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
            return jsonify({"error": "Parcela não encontrada ou já está paga"}), 404
            
        return jsonify({
            "success": True,
            "message": "Parcela marcada como paga com sucesso"
        })
    except Exception as e:
        app.logger.error(f"Erro ao marcar como pago: {str(e)}")
        return jsonify({"error": "Erro interno ao processar a requisição"}), 500

@app.route('/api/payments/<payment_id>', methods=['PUT'])
def update_payment(payment_id):
    if not db:
        return jsonify({"error": "Conexão com o banco de dados falhou"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "ID de parcela inválido"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dados não fornecidos"}), 400
        
        if errors := validate_payment_data(data, partial_update=True):
            return jsonify({"error": "Dados inválidos", "details": errors}), 400
        
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
            return jsonify({"error": "Parcela não encontrada ou nenhuma alteração feita"}), 404
            
        return jsonify({
            "success": True,
            "message": "Parcela atualizada com sucesso"
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"Erro ao atualizar parcela: {str(e)}")
        return jsonify({"error": "Erro interno ao processar a requisição"}), 500

@app.route('/api/payments/<payment_id>', methods=['DELETE'])
def delete_payment(payment_id):
    if not db:
        return jsonify({"error": "Conexão com o banco de dados falhou"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "ID de parcela inválido"}), 400
            
        result = db.payments.delete_one({"_id": ObjectId(payment_id)})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Parcela não encontrada"}), 404
            
        return jsonify({
            "success": True,
            "message": "Parcela excluída com sucesso"
        })
    except Exception as e:
        app.logger.error(f"Erro ao excluir parcela: {str(e)}")
        return jsonify({"error": "Erro interno ao processar a requisição"}), 500

# Rotas para servir o frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# Health check
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

# Configuração do servidor para produção
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
