# Fina

Sistema financeiro web com Flask + PostgreSQL, preparado para Render.

## Recursos
- Criação de conta e login com senha armazenada como hash.
- Entradas e saídas.
- Categorias de serviços e despesas.
- Parcelamento automático mensal.
- Saldo, entradas, saídas e valores pendentes.
- Histórico por usuário.
- Banco PostgreSQL persistente.

## Render
O arquivo `render.yaml` cria o Web Service e o PostgreSQL e injeta `DATABASE_URL` automaticamente. O Render suporta Blueprints para provisionar serviços e bancos a partir de um único YAML. Consulte a documentação oficial do Render antes do primeiro deploy.

O link público só existe depois que o Blueprint for criado/deployado na conta Render.
