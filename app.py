from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from datetime import datetime
import os
import certifi

app = Flask(__name__, static_folder='.', static_url_path='')

# Configuração do CORS (permitindo qualquer origem)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

# Definir o URI de conexão MongoDB diretamente no código
MONGO_URI = "mongodb+srv://leoimarques:nT8QO2rCaps1RzwL@cluster0.ji1shyl.mongodb.net/carne_astra?retryWrites=true&w=majority&tls=true&tlsAllowInvalidCertificates=true"
MONGO_DB_NAME = "carne_astra"  # Nome do banco de dados

# Conexão com o MongoDB
def get_mongo_client():
    try:
        # A opção 'tlsCAFile' pode ser útil se houver um problema com o certificado
        return MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB: {str(e)}")
        return None

client = get_mongo_client()
db = client.get_database(MONGO_DB_NAME) if client else None

# Função para servir o frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

# Funções auxiliares
def validate_payment_data(data, partial_update=False):
    required_fields = ['description', 'value', 'dueDate', 'payer'] if not partial_update else []
    errors = {}
    
    for field in required_fields:
        if field not in data or not data[field]:
            errors[field] = "Campo obrigatório"
    
    if 'value' in data and (not isinstance(data['value'], (int, float)) or data['value'] <= 0):
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
    if db is None:
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

# Outras rotas permanecem iguais...

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
