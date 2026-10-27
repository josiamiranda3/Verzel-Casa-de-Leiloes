# VERZEL --- Casa de Leilões

Aplicação full-stack para criação e gerenciamento de lotes, lances ao
vivo, carteira simulada, liquidação e auditoria pública de leilões.

## Sumário

-   [Funcionalidades](#funcionalidades)
-   [Stack e pré-requisitos](#stack-e-pré-requisitos)
-   [Execução local no Windows](#execução-local-no-windows)
-   [Configuração do banco e
    migrações](#configuração-do-banco-e-migrações)
-   [Contas de demonstração](#contas-de-demonstração)
-   [Testes automatizados](#testes-automatizados)
-   [Decisões técnicas e regras de
    negócio](#decisões-técnicas-e-regras-de-negócio)
-   [Auditoria e integridade](#auditoria-e-integridade)
-   [Deploy público](#deploy-público)
-   [Segurança antes da entrega](#segurança-antes-da-entrega)
-   [Uso de ferramentas de IA](#uso-de-ferramentas-de-ia)

## Funcionalidades

-   Cadastro e autenticação de arrematantes com token JWT e senha
    armazenada por hash.
-   Perfil de leiloeiro para criar e gerenciar os próprios lotes.
-   Busca de itens na Open Library e cadastro manual de lotes com URL
    pública de imagem.
-   Vitrine com filtros por situação e favoritos.
-   Atualização dos estados dos lotes agendados, ao vivo e encerrados.
-   Lances validados pelo backend, com histórico e mensagens para
    recusas.
-   Reserva do valor do lance líder e liberação da reserva quando ele é
    superado.
-   Carteira com saldo total, comprometido e disponível; depósito
    explicitamente simulado.
-   Prorrogação anti-sniping: lance aceito nos dois minutos finais
    prorroga o encerramento em dois minutos.
-   Liquidação do lote, débito do vencedor, crédito do leiloeiro e
    comprovante compartilhável.
-   Auditoria pública do histórico de lances, verificação da cadeia de
    hashes e checkpoint.
-   Tema claro/escuro.

> **Aviso:** depósitos e valores são simulados. A aplicação não processa
> pagamentos reais.

## Stack e pré-requisitos

Versões observadas no ambiente de desenvolvimento do projeto e faixas de
dependências declaradas:

  -----------------------------------------------------------------------
  Componente                          Versão/requisito
  ----------------------------------- -----------------------------------
  Sistema operacional                 Windows 10/11

  Python                              3.13.14 no ambiente de
                                      desenvolvimento; Python 3.12 também
                                      é compatível com o Dockerfile

  Node.js                             Node.js 24.x usado no
                                      desenvolvimento; instalar uma
                                      versão compatível com Vite 8

  npm                                 npm 11.x usado no desenvolvimento

  PostgreSQL                          PostgreSQL 16 recomendado

  Frontend                            React 19, TypeScript 6, Vite 8

  Backend                             FastAPI, Uvicorn, SQLAlchemy 2,
                                      Alembic, Pydantic Settings

  Driver PostgreSQL                   psycopg 3
  -----------------------------------------------------------------------

Também são úteis Git, VS Code e, se optar por executar o banco em
contêiner, Docker Desktop com Docker Compose.

## Execução local no Windows

Os comandos abaixo usam **Git Bash**. Se usar PowerShell, adapte a
ativação do ambiente virtual conforme indicado.

### 1. Obter o projeto

``` bash
git clone <URL_DO_REPOSITORIO>
cd casa-leiloes-verzel
```

Se você já tem o repositório local, entre na pasta do projeto em vez de
clonar novamente.

### 2. Configurar o banco PostgreSQL

Escolha uma das opções.

**Opção A --- PostgreSQL instalado localmente**

Crie um banco e um usuário exclusivos para desenvolvimento. Exemplo a
executar no `psql` com um usuário administrador (substitua a senha de
exemplo):

``` sql
CREATE USER verzel_dev WITH PASSWORD 'SUBSTITUA_POR_UMA_SENHA_LOCAL_FORTE';
CREATE DATABASE verzel OWNER verzel_dev;
```

Não use essa senha de exemplo em produção.

**Opção B --- Docker Compose**

Na raiz do projeto, confira primeiro as variáveis do
`docker-compose.yml` e gere valores locais próprios para
`POSTGRES_PASSWORD` e `JWT_SECRET_KEY`. Depois execute:

``` bash
docker compose up --build -d
docker compose ps
```

O Compose publica a aplicação web local na porta `8080` e a API na porta
`8001`. A URL de API usada no build do frontend do Compose é
`http://localhost:8001`, adequada somente para desenvolvimento local.

### 3. Configurar e iniciar o backend

Na raiz do projeto, abra um terminal:

``` bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

No PowerShell, ative o ambiente virtual com:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Edite `backend/.env` e informe os valores do seu banco local. Exemplo de
formato:

``` dotenv
DATABASE_URL=postgresql+psycopg://verzel_dev:SENHA_LOCAL@localhost:5432/verzel
JWT_SECRET_KEY=COLOQUE_AQUI_UM_SEGREDO_ALEATORIO_LONGO
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FRONTEND_ORIGIN=http://localhost:5173
```

Use uma senha URL-encoded na URL de conexão se ela contiver caracteres
reservados. Gere um segredo aleatório forte para `JWT_SECRET_KEY`; não
reutilize o valor de exemplo nem o publique.

A partir da pasta `backend`, aplique as migrações e inicie a API:

``` bash
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

A API estará em `http://localhost:8001`, a documentação interativa em
`http://localhost:8001/docs` e a verificação de saúde em
`http://localhost:8001/health`.

### 4. Configurar e iniciar o frontend

Em outro terminal:

``` bash
cd frontend
npm install
```

Crie `frontend/.env` com a URL da API local:

``` dotenv
VITE_API_URL=http://localhost:8001
```

Inicie o frontend:

``` bash
npm run dev
```

Abra `http://localhost:5173`.

> `VITE_API_URL` é incorporada ao frontend no momento do build. Em
> produção, configure-a antes de executar `npm run build` ou antes de o
> serviço de hospedagem construir o frontend.

## Configuração do banco e migrações

O esquema é gerenciado por Alembic. Sempre use a pasta `backend` para
executar os comandos.

Verificar a revisão atual:

``` bash
alembic current
```

Ver histórico:

``` bash
alembic history
```

Aplicar as migrações pendentes:

``` bash
alembic upgrade head
```

As migrações também são executadas no início do contêiner do backend
conforme o `backend/Dockerfile`.

### Dados iniciais e contas de demonstração

Não há no repositório um comando genérico de seed que crie
automaticamente uma coleção completa de usuários, carteiras e lotes de
demonstração. Para preparar dados controlados:

1.  Crie um arrematante pela interface ou use `POST /auth/register` na
    documentação `/docs`.

2.  Crie um leiloeiro de desenvolvimento executando o script interativo
    `backend/create_auctioneer.py`, com o backend configurado para
    apontar ao banco correto:

    ``` bash
    cd backend
    source .venv/Scripts/activate
    python create_auctioneer.py
    ```

3.  Entre com o perfil de leiloeiro e cadastre lotes de demonstração
    pela interface.

4.  Use contas e dados fictícios. Não publique senhas, tokens, dados
    pessoais ou contas privadas no README.

O cadastro público não deve permitir que alguém escolha livremente o
papel de leiloeiro. O script é uma ferramenta administrativa; não o
exponha como endpoint público.

## Contas de demonstração

Este repositório não define credenciais públicas fixas para
demonstração. Para a avaliação, crie contas de teste separadas e
registre as credenciais em um canal privado e seguro, se for necessário
compartilhá-las com avaliadores. Não coloque senhas reais ou tokens
neste arquivo, no Git ou em capturas de tela públicas.

Sugestão de preparação: - **Leiloeiro de demonstração:** conta criada
administrativamente e usada para publicar lotes. - **Arrematante A:**
conta criada pelo fluxo público para testar depósito simulado e
lances. - **Arrematante B:** segunda conta para testar disputa,
superação de lance e liberação de reserva.

Use valores fictícios e evite dados pessoais reais.

## Testes automatizados

A suíte do backend foi executada em Windows com Python 3.13.14 e pytest
9.1.1. O resultado registrado em 27/10/2026 foi **82 testes aprovados em
5,14 segundos**, sem falhas ou erros. Isso valida os cenários cobertos
pelos testes; não significa 100% de cobertura de código nem substitui
testes manuais.

Os testes de integração usam um PostgreSQL isolado. No ambiente atual, a
configuração de teste é validada pelo arquivo
`backend/tests/conftest.py` e espera uma base local de teste dedicada
`verzel_test`, usuário `verzel_test`, porta `5433`. **Nunca aponte a URL
de testes para o banco de desenvolvimento ou produção.**

Configure `TEST_DATABASE_URL` para o banco isolado e execute a partir de
`backend`:

``` bash
export TEST_DATABASE_URL="postgresql+psycopg://verzel_test:SENHA_TESTE@localhost:5433/verzel_test"
python -m pytest -v
```

Os testes mais recentes incluem encerramento de lotes agendados sem
lances, transição de lote agendado para ao vivo, lances concorrentes,
reservas de saldo, anti-sniping, liquidação e auditoria.

Verifique também o frontend:

``` bash
cd frontend
npm ci
npm run lint
npm run build
```

## Decisões técnicas e regras de negócio

### Organização da aplicação

-   **Frontend:** React + TypeScript + Vite. A URL base da API é
    configurada por `VITE_API_URL`.
-   **Backend:** FastAPI fornece endpoints REST e valida as regras no
    servidor; o frontend não é considerado autoridade para aceitar
    lances ou alterar saldos.
-   **Banco:** PostgreSQL persiste usuários, carteiras, lotes, lances,
    transações e eventos de auditoria.
-   **Migrações:** Alembic mantém o esquema versionado.
-   **Autenticação:** JWT Bearer e hashes de senha; rotas protegidas
    exigem autenticação e verificam o papel e a propriedade do recurso.

### Regras principais de leilão

-   Só são aceitos lances quando o lote está ao vivo, dentro do
    intervalo de início e encerramento.
-   O primeiro lance deve ser pelo menos igual ao lance inicial.
-   Lances seguintes devem atingir o lance atual acrescido do incremento
    mínimo.
-   O líder atual não pode cobrir o próprio lance.
-   O saldo disponível é o saldo total menos os valores comprometidos em
    lances.
-   Quando um novo lance supera o anterior, a reserva anterior é
    liberada e o novo valor fica comprometido.
-   Um lance aceito nos últimos dois minutos prorroga o encerramento em
    dois minutos (anti-sniping).
-   Ao encerrar, a liquidação transfere o valor simulado do vencedor
    para o leiloeiro e permite consultar o comprovante. Um lote sem
    lances é encerrado sem vencedor e sem pagamento.
-   Cancelamento e liquidação são validados no backend conforme o estado
    do lote e as permissões do usuário.
-   A integração com a API externa não deve impedir que as
    funcionalidades locais já disponíveis, como vitrine, auditoria e
    comprovante, continuem funcionando quando a API falhar.

## Auditoria e integridade

O backend registra eventos de negócio em uma cadeia de hashes SHA-256 e
oferece verificação pública do histórico de lances. Checkpoints ajudam a
detectar alterações que não seriam evidentes apenas pela verificação da
cadeia corrente.

A auditoria permite identificar inserção, remoção ou alteração de
eventos cobertos pelo mecanismo. Como em qualquer solução de auditoria,
as garantias dependem da proteção das credenciais e do checkpoint: não
se deve afirmar que um mecanismo local torna impossível toda adulteração
por um administrador com controle total do banco e de todos os artefatos
de verificação.

As respostas públicas de auditoria e os comprovantes devem evitar expor
dados pessoais desnecessários.

## Deploy público

O deploy público é obrigatório para o desafio. A aplicação publicada
deve funcionar sem depender de `localhost`.

Uma arquitetura simples para a entrega é: - **PostgreSQL:** Supabase ou
outro PostgreSQL gerenciado. - **Backend FastAPI:** serviço que suporte
Python/Docker, por exemplo Render. - **Frontend React/Vite:** hospedagem
estática, por exemplo Vercel ou Netlify.

Os nomes dos provedores são sugestões; o importante é configurar
corretamente as URLs públicas e validar o fluxo completo.

### Backend em produção

Configure as variáveis no painel do serviço de hospedagem, nunca em
arquivos versionados:

``` dotenv
DATABASE_URL=URL_DO_POSTGRESQL_DE_PRODUCAO
JWT_SECRET_KEY=SEGREDO_ALEATORIO_FORTE_E_EXCLUSIVO
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FRONTEND_ORIGIN=https://SEU-FRONTEND-PUBLICO
```

Use a URL de conexão fornecida pelo provedor PostgreSQL e, quando
exigido, habilite SSL conforme a configuração do provedor. Não use a URL
de banco de testes.

Comandos típicos para um serviço Python que constrói a partir da pasta
`backend`: - **Build/instalação:** `pip install -r requirements.txt` -
**Comando de inicialização:**
`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Se o provedor usar o `backend/Dockerfile`, ele já executa as migrações
antes de iniciar o Uvicorn. Confirme se a plataforma define a variável
`PORT` e adapte o comando de acordo com as instruções dela.

O middleware CORS atual aceita `http://localhost:5173` e a origem
definida por `FRONTEND_ORIGIN`. Configure esta última com a origem
pública exata do frontend, incluindo `https://` e sem caminhos como
`/login`. Se a hospedagem oferecer URLs de preview diferentes,
configure-as deliberadamente; não use `*` indiscriminadamente com
credenciais.

Após publicar, verifique: - `https://SUA-API-PUBLICA/health` -
`https://SUA-API-PUBLICA/docs`

### Frontend em produção

Configure a variável de build:

``` dotenv
VITE_API_URL=https://SUA-API-PUBLICA
```

-   **Diretório raiz/build:** `frontend`
-   **Comando de build:** `npm ci && npm run build`
-   **Diretório de saída:** `dist`

O frontend deve chamar a API pública, não `localhost:8001`. Em serviços
de hospedagem, configure `VITE_API_URL` nas variáveis de ambiente do
projeto e faça um novo deploy para que o valor seja incorporado ao
build.

### Banco de produção e dados iniciais

1.  Crie um banco PostgreSQL de produção separado dos bancos local e de
    teste.
2.  Configure `DATABASE_URL` no backend.
3.  Aplique `alembic upgrade head` antes de testar os endpoints.
4.  Crie as contas de demonstração usando os fluxos descritos em [Contas
    de demonstração](#contas-de-demonstração).
5.  Cadastre lotes fictícios e configure datas futuras para testar o
    fluxo ao vivo.
6.  Não copie dados pessoais ou credenciais de desenvolvimento para a
    produção.

### Checklist de validação após o deploy

-   [ ] A página inicial carrega usando a URL pública.
-   [ ] Cadastro e login funcionam.
-   [ ] A vitrine lista os lotes e seus estados.
-   [ ] O leiloeiro consegue criar e cancelar um lote elegível.
-   [ ] Um arrematante consegue fazer um depósito simulado.
-   [ ] Lances válidos são aceitos; lances inválidos são rejeitados com
    mensagem clara.
-   [ ] A reserva do líder é atualizada quando outro usuário supera o
    lance.
-   [ ] O anti-sniping funciona próximo do encerramento.
-   [ ] O lote encerra corretamente e pode ser liquidado pelo leiloeiro.
-   [ ] Meus arremates e o comprovante público funcionam.
-   [ ] A auditoria pública mostra o histórico e informa a integridade
    da cadeia.
-   [ ] A aplicação funciona em janela anônima ou outro dispositivo, sem
    depender de `localhost`.
-   [ ] CORS não bloqueia o frontend publicado e não está aberto
    indiscriminadamente.
-   [ ] Não há senhas, tokens, chaves privadas ou URLs com credenciais
    no repositório.

## Segurança antes da entrega

Antes de publicar: 1. Confirme que `.env`, `.venv`, `node_modules`,
dumps de banco, tokens e arquivos de credenciais estão ignorados pelo
Git. 2. Revise `git status --short` e os arquivos que serão enviados. 3.
Gere um `JWT_SECRET_KEY` exclusivo para produção. 4. Nunca use as
credenciais do banco de testes em produção. 5. Verifique o histórico do
Git se algum segredo já tiver sido commitado. Remover um segredo do
arquivo atual não o remove do histórico; se houve exposição,
rotacione-o. 6. Confirme que o cadastro público não permite criar
usuários com papel privilegiado. 7. Use contas e itens fictícios na
demonstração.

## Uso de ferramentas de IA

O desafio permite o uso de IA e solicita que isso seja declarado na
submissão. Informe honestamente quais ferramentas foram usadas, em quais
tarefas e o que foi revisado, testado ou ajustado manualmente. Não
declare tarefas que não foram realizadas.
