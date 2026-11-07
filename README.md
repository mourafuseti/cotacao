# Cotação Pro

MVP de uma plataforma B2B para empresas publicarem cotações e fornecedores enviarem propostas. A referência visual fornecida foi traduzida em uma interface responsiva com painel, fluxo de cotações e áreas separadas por perfil empresarial.

## Requisitos

- Python 3.12 ou superior
- Dependências de `requirements.txt`
- PostgreSQL opcional; SQLite é usado por padrão no desenvolvimento

## Executar localmente

No PowerShell, na pasta do projeto (crie o ambiente virtual se ainda não existir):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abra `http://127.0.0.1:8000/`. O acesso de empresa é feito com CNPJ e senha. O painel administrativo fica em `/admin/`. Crie o usuário administrativo com `python manage.py createsuperuser`.

O arquivo `.env.example` documenta as variáveis, mas não é carregado automaticamente. Configure-as no ambiente da hospedagem. Para produção, defina uma `SECRET_KEY` forte, `DEBUG=False`, `ALLOWED_HOSTS` e publique somente atrás de HTTPS. Com `DEBUG=False`, o projeto habilita redirecionamento para HTTPS, cookies seguros e HSTS por padrão. Se o TLS terminar em um proxy/load balancer, configure corretamente o encaminhamento de HTTPS no servidor antes de ativar o redirecionamento. Para usar PostgreSQL, configure `DB_ENGINE=postgresql` e `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e `DB_PORT`.

## Fluxo inicial

1. A empresa cria uma conta como compradora, fornecedora ou ambas.
2. A empresa importa o catálogo em Excel (.xlsx), confere a prévia e seleciona produtos ao criar cotações.
3. Compradoras publicam uma cotação com itens, quantidades, especificações e prazo.
4. Fornecedoras veem cotações abertas e enviam valor total, prazo de entrega e observações.
5. A compradora compara as propostas recebidas na página da cotação.

## Escopo do MVP

O catálogo aceita planilhas Excel `.xlsx` de até 10 MB e 5.000 produtos por importação. O arquivo precisa ter as colunas `ID do registro` e `Produto Estoque Nome`; número de pedidos, identificação, variação, marca, PN e bloqueio são reconhecidos quando presentes. Uma prévia é exibida antes da gravação; produtos são atualizados pelo par ID de origem + ID da variação, e os bloqueados não aparecem ao criar uma cotação. O número histórico de pedidos nunca é usado como quantidade solicitada.

O cadastro aceita CNPJ numérico e alfanumérico de 14 caracteres com validação dos dígitos verificadores. Ainda não inclui recuperação de senha, verificação documental, limitação de tentativas de login, notificações por e-mail, anexos ou contratação/pagamento. Esses itens devem ser definidos antes de abrir o sistema ao público ou usar em produção.
