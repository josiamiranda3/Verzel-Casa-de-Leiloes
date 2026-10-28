# VERZEL — Casa de Leilões

Aplicação full-stack para criação e gerenciamento de leilões online, com cadastro de lotes, disputa de lances, controle de saldo, liquidação simulada e auditoria da integridade dos eventos.

O projeto foi desenvolvido com React e TypeScript no frontend, FastAPI no backend e PostgreSQL como banco de dados. A arquitetura prioriza a validação das regras de negócio no servidor, a consistência das operações financeiras simuladas e a rastreabilidade das atividades realizadas durante os leilões.

> **Importante:** esta aplicação utiliza uma carteira e operações financeiras simuladas. Não processa pagamentos reais e não deve ser utilizada como plataforma financeira de produção sem as adaptações e validações necessárias.

## Sumário

- [1. Visão geral](#1-visão-geral)
- [2. Funcionalidades](#2-funcionalidades)
- [3. Tecnologias utilizadas](#3-tecnologias-utilizadas)
- [4. Arquitetura da aplicação](#4-arquitetura-da-aplicação)
- [5. Pré-requisitos](#5-pré-requisitos)
- [6. Configuração e execução local](#6-configuração-e-execução-local)
- [7. Banco de dados e migrações](#7-banco-de-dados-e-migrações)
- [8. Perfis e dados de demonstração](#8-perfis-e-dados-de-demonstração)
- [9. Regras de negócio](#9-regras-de-negócio)
- [10. Testes automatizados](#10-testes-automatizados)
- [11. Auditoria e integridade](#11-auditoria-e-integridade)
- [12. Deploy e configuração de produção](#12-deploy-e-configuração-de-produção)
- [13. Segurança e limitações conhecidas](#13-segurança-e-limitações-conhecidas)
- [14. Uso de inteligência artificial no desenvolvimento](#14-uso-de-inteligência-artificial-no-desenvolvimento)
- [15. Próximas evoluções](#15-próximas-evoluções)

## 1. Visão geral

O VERZEL — Casa de Leilões é uma aplicação web que simula o funcionamento de uma plataforma de leilões digitais.

A aplicação permite que usuários participem de disputas por lotes, acompanhem a evolução dos lances e consultem o histórico das operações. Os leiloeiros podem administrar seus próprios lotes, enquanto o backend controla as regras de participação, a disponibilidade de saldo e a finalização das disputas.

O projeto também implementa mecanismos de auditoria baseados em hashes criptográficos, permitindo verificar a integridade dos eventos registrados pelo sistema.

### Objetivos técnicos

- Construir uma aplicação full-stack com frontend e backend desacoplados.
- Aplicar autenticação e autorização para diferentes perfis de usuário.
- Implementar regras de negócio no servidor, sem depender da validação do navegador.
- Controlar reservas de saldo e disputas concorrentes por lotes.
- Utilizar migrações versionadas para administrar a estrutura do banco de dados.
- Registrar eventos de negócio para auditoria e rastreabilidade.
- Automatizar testes para validar os principais fluxos da aplicação.
- Preparar a aplicação para execução local e publicação em ambientes de hospedagem.

## 2. Funcionalidades

### Autenticação e usuários

- Cadastro de usuários.
- Autenticação com tokens JWT.
- Armazenamento de senhas por meio de hashes.
- Proteção de rotas que exigem autenticação.
- Separação de permissões entre arrematantes e leiloeiros.

### Gerenciamento de lotes

- Cadastro de lotes pelo perfil de leiloeiro.
- Associação dos lotes aos seus respectivos proprietários.
- Cadastro manual de itens.
- Integração com a Open Library para consulta de informações de livros, conforme a implementação disponível.
- Utilização de URLs públicas para imagens dos itens.
- Exibição dos lotes em uma vitrine com filtros por situação.
- Gerenciamento dos estados dos lotes.
- Cancelamento de lotes conforme as regras de negócio e as permissões aplicáveis.

### Disputas e lances

- Validação de lances no backend.
- Verificação do estado e do período de realização do leilão.
- Aplicação de lance mínimo e incremento mínimo.
- Impedimento de que o líder atual cubra o próprio lance.
- Registro do histórico de lances.
- Retorno de mensagens para lances recusados.
- Liberação da reserva anterior quando outro participante assume a liderança.
- Prorrogação automática do encerramento em situações de anti-sniping.

### Carteira e liquidação simulada

- Consulta do saldo total, comprometido e disponível.
- Depósitos simulados.
- Reserva do valor correspondente ao lance líder.
- Liberação de valores reservados quando o participante perde a liderança.
- Débito simulado do vencedor durante a liquidação.
- Crédito simulado ao leiloeiro.
- Consulta dos arremates e dos comprovantes disponíveis.

### Auditoria

- Registro de eventos de negócio.
- Encadeamento de hashes SHA-256.
- Consulta pública do histórico de lances, conforme as permissões de exposição definidas.
- Verificação da integridade da cadeia de eventos.
- Utilização de checkpoints para apoiar a detecção de alterações nos registros.

### Interface

- Interface web construída com React e TypeScript.
- Tema claro e escuro.
- Vitrine de lotes.
- Consulta de favoritos, conforme a funcionalidade implementada.
- Telas para acompanhamento dos leilões e consulta dos resultados.

> A disponibilidade de cada funcionalidade deve ser confirmada na versão efetivamente publicada. As descrições acima documentam o escopo informado para o projeto, não substituindo a validação da aplicação executável.

## 3. Tecnologias utilizadas

| Camada | Tecnologias |
|---|---|
| Frontend | React, TypeScript e Vite |
| Estilização e interface | CSS e recursos de interface do frontend |
| Backend | Python, FastAPI e Uvicorn |
| Validação de dados | Pydantic |
| ORM | SQLAlchemy |
| Banco de dados | PostgreSQL |
| Migrações | Alembic |
| Autenticação | JWT e hash de senhas |
| Testes | pytest |
| Integração externa | Open Library |
| Versionamento | Git e GitHub |
| Ambiente de desenvolvimento | Windows, VS Code e terminais de desenvolvimento |
| Contêineres | Docker e Docker Compose, quando utilizados |

### Versões de referência

As versões abaixo correspondem ao ambiente de desenvolvimento registrado no projeto. Antes de reproduzir a instalação, confira também os arquivos de dependências e a configuração do Docker.

| Componente | Referência |
|---|---|
| Python | 3.13.14 no ambiente de desenvolvimento |
| Node.js | 24.x |
| npm | 11.x |
| PostgreSQL | 16 recomendado |
| React | 19 |
| TypeScript | 6 |
| Vite | 8 |
| SQLAlchemy | 2.x |
| Driver PostgreSQL | psycopg 3 |

As versões efetivamente instaladas devem ser verificadas em `package-lock.json`, `requirements.txt`, `pyproject.toml` (se existente) e nos arquivos Docker do repositório.

## 4. Arquitetura da aplicação

A aplicação utiliza uma arquitetura separada em frontend, backend e banco de dados.

```text
┌─────────────────────────────────┐
│       Usuário / Navegador       │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│       Frontend React/TS         │
│                                 │
│  Interface, formulários e       │
│  comunicação com a API          │
└────────────────┬────────────────┘
                 │ HTTP / JSON
                 ▼
┌─────────────────────────────────┐
│          Backend FastAPI        │
│                                 │
│ Autenticação e autorização      │
│ Validação das regras de negócio │
│ Lances e reservas de saldo      │
│ Liquidação e auditoria          │
└────────────────┬────────────────┘
                 │ SQLAlchemy
                 ▼
┌─────────────────────────────────┐
│          PostgreSQL             │
│                                 │
│ Usuários, carteiras, lotes,     │
│ lances, transações e eventos    │
└─────────────────────────────────┘
```

### Responsabilidades de cada camada

**Frontend**

Responsável por apresentar os dados, receber as interações do usuário e consumir os endpoints da API. A interface não é considerada autoridade para determinar se um lance é válido ou se um saldo pode ser utilizado.

**Backend**

Responsável por autenticar usuários, verificar permissões, validar as operações, aplicar as regras do leilão e persistir as alterações. Operações que envolvem saldo e concorrência devem ser coordenadas no servidor e protegidas por transações e mecanismos adequados de consistência.

**Banco de dados**

Responsável pela persistência dos dados e pelas restrições estruturais definidas no esquema. As migrações Alembic permitem versionar e aplicar as alterações da estrutura do banco.

### Estrutura de diretórios

A estrutura resumida esperada é a seguinte. Consulte o repositório para confirmar os nomes e arquivos exatos da versão publicada.

```text
casa-leiloes-verzel/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   ├── routes/       # ou estrutura equivalente de rotas
│   │   ├── schemas/
│   │   ├── services/     # conforme a organização implementada
│   │   └── main.py
│   ├── tests/
│   ├── alembic/
│   ├── alembic.ini
│   ├── create_auctioneer.py
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── package-lock.json
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 5. Pré-requisitos

Para executar a aplicação localmente, instale:

- Git.
- Python em uma versão compatível com as dependências do backend.
- Node.js e npm compatíveis com a versão do Vite utilizada.
- PostgreSQL, localmente ou em um serviço gerenciado.
- Um editor de código, como Visual Studio Code.

Docker Desktop e Docker Compose são opcionais quando o projeto é executado com serviços locais instalados diretamente.

## 6. Configuração e execução local

Os comandos a seguir utilizam Git Bash no Windows, salvo indicação em contrário.

### 6.1. Obter o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd casa-leiloes-verzel
```

Substitua `<URL_DO_REPOSITORIO>` pela URL real do repositório.

Se o projeto já estiver na sua máquina, entre na pasta existente.

### 6.2. Criar o banco de dados

Crie um banco e um usuário exclusivos para o desenvolvimento.

No `psql`, utilizando uma conta administrativa:

```sql
CREATE USER verzel_dev WITH PASSWORD 'SENHA_LOCAL_FORTE';
CREATE DATABASE verzel OWNER verzel_dev;
```

Substitua a senha de exemplo por uma senha local própria.

Se utilizar Supabase ou outro PostgreSQL gerenciado, crie ou selecione um banco de desenvolvimento e obtenha a URL de conexão apropriada.

### 6.3. Configurar o backend

Entre na pasta do backend:

```bash
cd backend
```

Crie e ative o ambiente virtual:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

No PowerShell, utilize:

```powershell
.\.venv\Scripts\Activate.ps1
```

Atualize o instalador e instale as dependências:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copie o arquivo de exemplo das variáveis de ambiente:

```bash
cp .env.example .env
```

No PowerShell, caso necessário:

```powershell
Copy-Item .env.example .env
```

Edite `backend/.env` e configure os valores para o ambiente local.

Exemplo ilustrativo:

```dotenv
DATABASE_URL=postgresql+psycopg://verzel_dev:SENHA_LOCAL@localhost:5432/verzel
JWT_SECRET_KEY=SUBSTITUA_POR_UM_SEGREDO_ALEATORIO
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FRONTEND_ORIGIN=http://localhost:5173
```

Utilize as variáveis efetivamente reconhecidas pela configuração do backend. O exemplo não substitui a conferência de `app/core/config.py` ou do módulo equivalente.

**Cuidados importantes:**

- Gere um segredo aleatório exclusivo para `JWT_SECRET_KEY`.
- Não utilize as credenciais de produção no ambiente local.
- Se a senha do banco contiver caracteres reservados, faça o devido URL encoding.
- Não versione o arquivo `.env`.

### 6.4. Aplicar as migrações

Ainda na pasta `backend`, execute:

```bash
alembic upgrade head
```

O comando aplica as migrações pendentes e prepara o esquema do banco de dados.

### 6.5. Iniciar a API

Execute:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Quando a inicialização for bem-sucedida, os endereços locais esperados são:

| Recurso | Endereço |
|---|---|
| API | `http://localhost:8001` |
| Documentação interativa | `http://localhost:8001/docs` |
| Verificação de saúde | `http://localhost:8001/health` |

Esses endereços pressupõem que as rotas correspondentes estejam implementadas e que a API tenha iniciado corretamente.

Mantenha o terminal do backend aberto.

### 6.6. Configurar o frontend

Abra outro terminal na raiz do projeto:

```bash
cd frontend
npm install
```

Configure a URL da API no arquivo `frontend/.env`:

```dotenv
VITE_API_URL=http://localhost:8001
```

Inicie o servidor de desenvolvimento:

```bash
npm run dev
```

Acesse:

`http://localhost:5173`

A porta pode variar conforme a configuração do Vite.

A variável `VITE_API_URL` é incorporada ao build do frontend. Portanto, qualquer alteração nessa variável exige reiniciar o servidor de desenvolvimento ou gerar um novo build, conforme o ambiente utilizado.

### 6.7. Executar com Docker Compose

Se o repositório incluir um `docker-compose.yml` funcional, também será possível utilizar os contêineres.

Antes de executar, confira os serviços, as portas, os volumes e as variáveis de ambiente definidos no arquivo.

Depois de configurar os segredos locais:

```bash
docker compose up --build -d
docker compose ps
```

Para acompanhar os logs:

```bash
docker compose logs -f
```

Para encerrar os serviços:

```bash
docker compose down
```

A configuração registrada para o projeto prevê o frontend na porta `8080` e a API na porta `8001`. Confirme essas portas no Compose antes de utilizá-las.

Não execute simultaneamente diferentes configurações de banco de dados sem verificar qual instância cada serviço está utilizando.

## 7. Banco de dados e migrações

A estrutura do banco é administrada por Alembic, integrado ao SQLAlchemy.

O esquema registrado no projeto inclui entidades para:

- Usuários.
- Carteiras.
- Lotes.
- Lances.
- Transações de carteira.
- Eventos de auditoria.

Os nomes e as restrições exatas devem ser conferidos nos modelos e nas migrações versionadas.

### Comandos úteis

Executar as migrações pendentes:

```bash
alembic upgrade head
```

Consultar a revisão aplicada:

```bash
alembic current
```

Consultar o histórico:

```bash
alembic history
```

Verificar o estado da migração:

```bash
alembic heads
```

Execute esses comandos na pasta `backend`, com o ambiente virtual ativado e as variáveis de ambiente apontando para o banco correto.

**Atenção:** nunca execute testes destrutivos contra o banco de produção.

## 8. Perfis e dados de demonstração

A demonstração da aplicação deve utilizar contas e dados fictícios.

### Arrematante

O arrematante participa dos leilões, acompanha seus lances e consulta sua carteira e seus arremates, de acordo com as permissões implementadas.

Crie uma conta pela interface ou pelo endpoint de cadastro documentado na API.

### Leiloeiro

O leiloeiro administra os próprios lotes, observadas as regras de autorização e de estado do sistema.

O repositório disponibiliza, conforme a configuração informada, o script administrativo `backend/create_auctioneer.py`.

Para utilizá-lo:

```bash
cd backend
source .venv/Scripts/activate
python create_auctioneer.py
```

O script deve ser executado somente em um ambiente controlado, apontando para o banco correto.

Não disponibilize a criação de usuários privilegiados como uma operação pública sem controles de autorização.

### Cenário de demonstração recomendado

Prepare três contas de teste:

1. **Leiloeiro:** publica lotes fictícios.
2. **Arrematante A:** realiza um depósito simulado e oferece lances.
3. **Arrematante B:** disputa os mesmos lotes e supera os lances anteriores.

Com esse cenário, é possível demonstrar a evolução dos lances, a liberação de reservas, o encerramento dos lotes e a consulta dos registros de auditoria.

Não publique senhas, tokens ou dados pessoais de contas privadas no README.

## 9. Regras de negócio

### Validação de lances

Os lances devem ser validados pelo backend. Entre as regras documentadas para o projeto estão:

- O lote precisa estar no estado adequado para receber lances.
- A operação precisa ocorrer dentro do período permitido.
- O primeiro lance deve respeitar o valor mínimo de abertura.
- Os lances seguintes devem respeitar o incremento mínimo.
- O líder atual não pode cobrir o próprio lance.
- O participante precisa ter saldo disponível suficiente.
- A operação deve respeitar as permissões do usuário.

A interface pode antecipar algumas validações para melhorar a experiência, mas a decisão final pertence ao servidor.

### Reserva de saldo

O saldo disponível corresponde ao saldo total menos os valores comprometidos.

Quando um participante assume a liderança, o valor necessário fica reservado. Se outro participante oferecer um lance superior e válido, a reserva anterior deve ser liberada e a nova reserva deve ser estabelecida.

Essas operações precisam ser protegidas contra concorrência para evitar reservas inconsistentes ou utilização duplicada do saldo.

### Anti-sniping

A regra documentada prevê que um lance aceito nos dois minutos finais do lote prorrogue o encerramento por mais dois minutos.

O comportamento deve ser validado com testes que considerem o horário do servidor, os limites do período e lances concorrentes.

### Encerramento e liquidação

Quando o lote é encerrado:

- Um lote sem lances termina sem vencedor e sem transferência de valores.
- Um lote com vencedor pode seguir o fluxo de liquidação permitido.
- O valor simulado é debitado do vencedor e creditado ao leiloeiro.
- O sistema disponibiliza o comprovante previsto para a operação.

A liquidação deve ser idempotente ou possuir controles equivalentes que impeçam a transferência duplicada em caso de requisições repetidas.

### Falhas em integrações externas

A integração com a Open Library deve ser tratada como uma dependência externa. Uma indisponibilidade do serviço não deve interromper funcionalidades locais que não dependam dessa integração.

O cadastro manual de lotes pode servir como alternativa quando esse fluxo estiver implementado e disponível.

## 10. Testes automatizados

O backend utiliza pytest para automatizar cenários de validação.

Segundo o registro de execução informado para o projeto, em 27 de outubro de 2026, a suíte do backend apresentou **82 testes aprovados em 5,14 segundos**, utilizando Python 3.13.14 e pytest 9.1.1.

Esse resultado corresponde à execução registrada. Para uma entrega pública, recomenda-se executar novamente os testes na versão final do código e atualizar esta informação caso o resultado seja diferente.

### Executar os testes do backend

Entre na pasta `backend`, ative o ambiente virtual e configure a base de teste isolada.

A configuração registrada utiliza PostgreSQL com o banco `verzel_test`, usuário `verzel_test` e porta `5433`. Confirme os valores em `backend/tests/conftest.py` antes de executar.

No Git Bash:

```bash
export TEST_DATABASE_URL="postgresql+psycopg://verzel_test:SENHA_TESTE@localhost:5433/verzel_test"
python -m pytest -v
```

No PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://verzel_test:SENHA_TESTE@localhost:5433/verzel_test"
python -m pytest -v
```

Ajuste a URL conforme as variáveis realmente utilizadas pela suíte.

**Não aponte a configuração de testes para o banco de desenvolvimento ou de produção.** Se os testes criarem ou removerem tabelas, utilize uma instância descartável e exclusiva.

### Cenários de teste relevantes

A suíte registrada inclui cenários relacionados a:

- Encerramento de lotes agendados sem lances.
- Transição de lotes agendados para o estado ao vivo.
- Lances concorrentes.
- Reservas e liberação de saldo.
- Regras de anti-sniping.
- Liquidação.
- Auditoria.

A lista acima não implica cobertura integral de todos os componentes ou de todos os cenários de falha.

### Verificar o frontend

Na pasta `frontend`:

```bash
npm ci
npm run lint
npm run build
```

O comando `npm ci` exige um arquivo de lock compatível com o `package.json`.

Se o projeto não possuir um script `lint`, verifique os scripts disponíveis em `frontend/package.json` antes de executar o comando.

Uma compilação bem-sucedida confirma que o build foi concluído; não substitui testes de interface, integração ou validação manual.

## 11. Auditoria e integridade

O projeto registra eventos de negócio em uma cadeia de hashes SHA-256. O mecanismo permite verificar a relação entre eventos encadeados e detectar determinadas alterações no histórico.

A solução também prevê checkpoints, que auxiliam na comparação da cadeia registrada com referências de integridade previamente estabelecidas.

### Objetivos do mecanismo

- Apoiar a rastreabilidade das operações.
- Detectar alterações em eventos cobertos pela cadeia de hashes.
- Permitir a verificação do histórico de lances.
- Facilitar a investigação de inconsistências nos registros.

### Limitações

Uma cadeia de hashes não é, por si só, garantia absoluta de imutabilidade.

Se um agente tiver controle total sobre o banco e sobre todos os artefatos utilizados para verificar a integridade, poderá existir a possibilidade de reconstruir registros e hashes. A força da auditoria depende também da proteção das credenciais, da preservação dos checkpoints e da separação entre os dados auditados e as referências de verificação.

Os endpoints públicos de auditoria e os comprovantes devem expor somente os dados necessários, evitando a divulgação de informações pessoais ou credenciais.

## 12. Deploy e configuração de produção

A publicação pública faz parte dos requisitos de entrega do desafio. Antes de divulgar a aplicação, é necessário validar o frontend, o backend, o banco de dados e os fluxos de negócio no ambiente publicado.

### Arquitetura sugerida

| Componente | Opção de hospedagem |
|---|---|
| Frontend React/Vite | Vercel ou Netlify |
| Backend FastAPI | Render ou outro serviço compatível com Python/Docker |
| PostgreSQL | Supabase ou outro provedor PostgreSQL gerenciado |

Esses provedores são sugestões de arquitetura, não uma confirmação de que o deploy já foi realizado.

### 12.1. Banco de produção

1. Crie um banco separado dos ambientes local e de teste.
2. Configure as credenciais e a URL de conexão do banco.
3. Habilite SSL conforme os requisitos do provedor.
4. Aplique as migrações antes de disponibilizar os fluxos que dependem das tabelas.
5. Configure backups e monitore a disponibilidade do banco.

Não reutilize credenciais ou dados privados de desenvolvimento.

### 12.2. Backend

Configure as variáveis de ambiente no painel do serviço:

```dotenv
DATABASE_URL=URL_DO_POSTGRESQL_DE_PRODUCAO
JWT_SECRET_KEY=SEGREDO_ALEATORIO_EXCLUSIVO
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FRONTEND_ORIGIN=https://SEU-FRONTEND-PUBLICO
```

Utilize os nomes e formatos efetivamente suportados pelo backend.

Um comando de inicialização possível, caso seja compatível com o ambiente e com a configuração do projeto, é:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

Confirme se o provedor disponibiliza a variável `PORT`. No Docker, confira o `Dockerfile` e o `ENTRYPOINT` para evitar executar as migrações duas vezes ou iniciar o servidor com configurações incompatíveis.

Migrações de produção devem ser tratadas como operações controladas. Para ambientes com múltiplas instâncias, prefira executá-las em uma etapa de release ou em um processo dedicado, quando suportado pelo provedor.

### 12.3. CORS

A configuração do backend deve permitir a origem pública exata do frontend.

No ambiente local, a origem utilizada é:

```text
http://localhost:5173
```

Em produção, configure a origem HTTPS do domínio publicado, por exemplo:

```text
https://seu-projeto.vercel.app
```

O endereço acima é ilustrativo. Utilize a URL real da aplicação.

Não habilite origens indiscriminadas apenas para contornar erros de integração. Caso existam URLs de preview, avalie quais precisam ser autorizadas.

### 12.4. Frontend

Configure a variável de build:

```dotenv
VITE_API_URL=https://SUA-API-PUBLICA
```

Na configuração de hospedagem, os valores esperados são:

- Diretório raiz: `frontend`.
- Comando de instalação e build: `npm ci && npm run build`.
- Diretório de saída: `dist`.

Confirme as opções exigidas pelo provedor e o conteúdo de `frontend/package.json`.

**A URL da API não pode apontar para `localhost` em uma aplicação acessada pela internet.** Variáveis com prefixo `VITE_` são incorporadas ao código disponibilizado ao navegador e não devem conter segredos.

### 12.5. Validação após a publicação

Depois de realizar o deploy:

- Verifique se a página inicial carrega.
- Confirme se o frontend alcança a API pública.
- Teste o cadastro e o login.
- Crie e consulte lotes.
- Teste depósitos simulados e lances.
- Verifique reservas e liberações de saldo.
- Teste encerramento e liquidação.
- Consulte os comprovantes e o histórico de auditoria.
- Teste as permissões dos diferentes perfis.
- Repita os testes em uma janela anônima ou em outro dispositivo.

Os endpoints `/health` e `/docs` podem ajudar a validar a API se estiverem disponíveis no ambiente publicado. Avalie se a documentação interativa deve permanecer acessível publicamente em produção.

## 13. Segurança e limitações conhecidas

Antes de disponibilizar o projeto:

- Confirme que `.env`, `.venv`, `node_modules`, arquivos de credenciais e dumps locais não serão publicados.
- Revise os arquivos incluídos no commit.
- Gere segredos exclusivos para produção.
- Verifique se o cadastro público não permite atribuição indevida de privilégios.
- Confirme que as rotas verificam autenticação, autorização e propriedade dos recursos.
- Proteja operações de saldo, lances e liquidação contra concorrência e repetição indevida.
- Evite registrar senhas, tokens ou dados pessoais desnecessários nos logs.
- Verifique as dependências e mantenha os pacotes atualizados.
- Confirme que o banco de testes está isolado do banco de produção.
- Revise o histórico do Git caso alguma credencial já tenha sido versionada e rotacione os segredos expostos.

### Limitações funcionais e operacionais

A aplicação é uma plataforma de demonstração e avaliação técnica.

Os valores da carteira e as transferências são simulados. O mecanismo de auditoria oferece verificabilidade dentro das garantias de sua implementação, mas não equivale a armazenamento imutável independente. A disponibilidade pública, a resiliência operacional, a cobertura de testes e a segurança do ambiente dependem de validações adicionais.

Não se deve apresentar a aplicação como um serviço financeiro pronto para operação comercial apenas porque os principais fluxos de demonstração funcionam.

## 14. Uso de inteligência artificial no desenvolvimento

Ferramentas de inteligência artificial foram utilizadas como apoio ao processo de desenvolvimento do VERZEL — Casa de Leilões, contribuindo para a organização do trabalho, a análise técnica e a implementação da aplicação.

A IA foi utilizada como ferramenta de assistência ao desenvolvimento, e não como substituta da validação do código ou da responsabilidade técnica sobre o resultado entregue.

### Principais formas de utilização

**1. Planejamento e estruturação do projeto**

A IA auxiliou na organização inicial do projeto, na definição dos componentes necessários e no planejamento da separação entre frontend, backend e banco de dados.

**2. Apoio às decisões de arquitetura**

A IA auxiliou na análise de alternativas técnicas e na discussão de decisões relacionadas à utilização de React, TypeScript, FastAPI, SQLAlchemy, PostgreSQL e Alembic, considerando as necessidades de persistência, autenticação e regras de negócio.

**3. Apoio à implementação**

A IA foi utilizada para auxiliar na elaboração e revisão de código, na estruturação de componentes e módulos e na implementação dos fluxos funcionais da aplicação, conforme as necessidades identificadas durante o desenvolvimento.

**4. Análise de problemas e depuração**

A ferramenta auxiliou na interpretação de mensagens de erro, na análise de problemas de configuração e na orientação para correções durante a instalação de dependências, a configuração do ambiente e a execução das migrações.

**5. Regras de negócio e consistência**

A IA apoiou a análise de cenários relacionados à validação de lances, ao controle de saldo, à concorrência, ao encerramento dos lotes e à auditoria, ajudando a identificar situações que precisavam de tratamento ou testes específicos.

**6. Testes e validação técnica**

A IA foi utilizada como apoio na análise dos cenários de teste, na interpretação dos resultados e na investigação de falhas. A aprovação dos testes deve ser demonstrada pelos resultados efetivamente obtidos na execução do projeto.

**7. Documentação e preparação para entrega**

A ferramenta auxiliou na organização deste README, na documentação das instruções de execução e na preparação das orientações de configuração e publicação.

### Responsabilidade e validação

As sugestões geradas por IA precisam ser confrontadas com o código, as dependências e os requisitos reais da aplicação. A ferramenta pode produzir instruções incorretas, soluções incompletas ou recomendações incompatíveis com o ambiente.

Por isso, o resultado deve ser validado por meio da revisão do código, da execução dos testes e da verificação prática dos fluxos da aplicação.

A utilização da IA não constitui, por si só, evidência de que uma funcionalidade foi concluída, de que um teste passou ou de que o deploy está funcionando.

A declaração acima descreve as categorias de assistência utilizadas no desenvolvimento. A submissão deve manter apenas as atividades que correspondam efetivamente ao processo realizado e identificar as ferramentas utilizadas conforme as exigências do desafio.

## 15. Próximas evoluções

As seguintes melhorias podem ser consideradas para futuras versões, conforme os resultados da validação e as prioridades do projeto:

- Testes de integração e de concorrência mais abrangentes.
- Testes automatizados de interface e fluxos ponta a ponta.
- Melhorias na observabilidade, nos logs e no monitoramento.
- Estratégias de recuperação e backup do banco de dados.
- Revisão de segurança e análise de dependências.
- Melhorias de acessibilidade e experiência do usuário.
- Separação e proteção independente das referências de auditoria.
- Pipeline de integração contínua para testes e build.
- Documentação adicional dos endpoints e dos contratos da API.
- Preparação para integração com serviços reais de pagamento, somente mediante implementação, requisitos de segurança e validações específicas.

---

**Status da documentação:** este README descreve a arquitetura, os fluxos e os procedimentos informados para o projeto. Antes da submissão, os comandos, as variáveis de ambiente, as funcionalidades e os resultados de testes devem ser conferidos na versão final do repositório.
