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
4. Compradoras podem informar destino, prazo desejado de entrega e garantia mínima; o prazo para receber propostas é apresentado separadamente.
5. Fornecedoras informam preço unitário e quantidade de cada item, frete, prazo, garantia, validade, impostos, disponibilidade e condições de pagamento.
6. A compradora compara os totais de produtos + frete, encerra o recebimento, registra a justificativa e seleciona uma proposta.
7. O histórico registra publicação, recebimento de propostas, encerramento, decisão e cancelamento.
8. Administradores convidam membros para a equipe por e-mail, com papéis de cotador, fornecedor ou somente leitura.

## Escopo do MVP

O catálogo aceita planilhas Excel `.xlsx` de até 10 MB e 5.000 produtos por importação. O arquivo precisa ter as colunas `ID do registro` e `Produto Estoque Nome`; número de pedidos, identificação, variação, marca, PN e bloqueio são reconhecidos quando presentes. Uma prévia é exibida antes da gravação; produtos são atualizados pelo par ID de origem + ID da variação, e os bloqueados não aparecem ao criar uma cotação. O número histórico de pedidos nunca é usado como quantidade solicitada.

O cadastro aceita CNPJ numérico e alfanumérico de 14 caracteres com validação dos dígitos verificadores. O login aceita CNPJ ou e-mail. A plataforma inclui confirmação de e-mail, recuperação de senha, proteção temporária após cinco tentativas de login incorretas, convites de equipe e notificações de publicação, proposta e decisão. E-mails de prazo podem ser enviados pelo comando `python manage.py send_quote_deadline_reminders`, que deve ser agendado para execução periódica no servidor.

As propostas são totalizadas a partir das linhas informadas, sem aceitar um subtotal digitado pelo fornecedor. A exportação CSV está disponível para os usuários compradores da empresa e protege células que poderiam ser interpretadas como fórmulas por planilhas. A interface de análise apresenta histórico e critérios da decisão.

## E-mail e produção

Em desenvolvimento, os e-mails são exibidos no console do servidor. Em produção, configure `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS` e os valores SMTP do `.env.example`; o serviço precisa permitir o envio pelo endereço definido em `DEFAULT_FROM_EMAIL`. Também use HTTPS e um banco PostgreSQL gerenciado para produção. Convites e confirmação de e-mail dependem de entrega de e-mail funcional.

A validação de CNPJ verifica formato e dígitos verificadores; ela não consulta a Receita Federal nem comprova a existência ou situação cadastral da empresa. Anexos, assinatura de contratos e pagamentos não fazem parte do escopo atual.
