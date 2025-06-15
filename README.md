# API Firebird - Railway

API simples em Python + Flask para consultar dados de um banco Firebird.

## 🔧 Variáveis de Ambiente:

- DB_HOST → IP ou domínio do servidor Firebird
- DB_DATABASE → Caminho completo do arquivo .FDB
- DB_USER → Usuário do Firebird (ex.: SYSDBA)
- DB_PASSWORD → Senha do Firebird
- DB_PORT → Porta (default 3050)
- API_TOKEN → Token para autenticação (ex.: 123456)

## 🚀 Endpoints:

### ✔️ Teste
`GET /`
- Retorna: "API Firebird está online"

### ✔️ Executar SELECT
`GET /query?sql=SEU_SQL`
- Header: `Authorization: Bearer SEU_TOKEN`
- Exemplo:
```
GET https://seu-app.up.railway.app/query?sql=SELECT * FROM CLIENTES
Header: Authorization: Bearer 123456
```

## 🚨 Segurança:
- Só aceita SELECT.
- Necessário autenticação via token.