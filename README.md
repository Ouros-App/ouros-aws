# ouros-aws

Automação de healthcheck para iniciar o AWS Academy Learner Lab pelo Canvas/Vocareum e disponibilizar as credenciais fornecidas pelo laboratório ao job do GitHub Actions.

## Arquitetura

O workflow lê as credenciais do Canvas e a região da AWS do Infisical (`/aws-academy`), automatiza Canvas e Vocareum com Playwright, abre **Details → AWS: Show** e grava as credenciais somente no ambiente do runner. O painel atual fornece access key e secret key; se também fornecer um session token, ele será exportado. Em seguida, o fluxo valida a sessão com `aws sts get-caller-identity`. As credenciais não são gravadas em artefatos nem no repositório.

## Configuração

No GitHub → Settings → Secrets and variables → Actions, cadastre os cinco itens abaixo como **Secrets**, com os nomes exatamente assim:

| Secret GitHub | Valor esperado |
| --- | --- |
| `INFISICAL_TOKEN` | Token de acesso aceito pela CLI do Infisical |
| `INFISICAL_PROJECT_ID` | ID do projeto Infisical (não o slug) |
| `INFISICAL_ENV` | Slug do ambiente, por exemplo `dev` ou `prod` |
| `INFISICAL_PATH` | Path dos secrets, por exemplo `/aws-academy` |
| `INFISICAL_HOST` | URL da instalação, por exemplo `https://app.infisical.com` |

O token deve ter permissão de leitura somente no projeto, ambiente e path necessários. Os workflows passam esses valores à Infisical CLI e carregam as configurações do Canvas no processo do bootstrap.

No Infisical, crie no path `/aws-academy`:

| Secret | Obrigatório | Uso |
| --- | --- | --- |
| `CANVAS_USERNAME` | sim | Login Canvas |
| `CANVAS_PASSWORD` | sim | Senha Canvas |
| `CANVAS_LOGIN_URL` | sim | URL do login institucional |
| `AWS_REGION` | não | Região padrão, default `us-east-1` |
| `CANVAS_COURSE_NAME` | não | Nome do curso |
| `CANVAS_LAB_LINK_TEXT` | não | Link do módulo Canvas; padrão `Sandbox Environment` |

O login institucional pode exigir MFA ou CAPTCHA. O fluxo não tenta contornar esses controles; se forem apresentados, o healthcheck falhará e será necessário um fluxo permitido pela instituição.

## Healthcheck

Execute manualmente **AWS Academy healthcheck** em Actions → workflow_dispatch. O job instala Chromium, carrega configuração do Infisical, inicia o laboratório e valida a identidade STS. Nenhum deploy é feito.

Para desenvolvimento local, instale Python, AWS CLI e Playwright, carregue as variáveis por um mecanismo seguro e rode:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m academy.bootstrap
```

Localmente, `GITHUB_ENV` não existe e o bootstrap recusa imprimir credenciais. Para validar manualmente, adapte o uso para um mecanismo temporário seguro; não salve as credenciais em arquivos persistentes.

## Deploy S3

O workflow **Deploy to S3** é manual e restrito à branch `main`. Informe um diretório de saída já construído e um bucket existente permitido pelo Learner Lab. Ele sincroniza com `--delete`; revise o bucket antes de executar. A infraestrutura S3 de referência está em `terraform/s3`, mas o workflow não cria recursos implicitamente.

## EC2

O workflow **Deploy to EC2 (Terraform)** prepara a sessão e valida a configuração Terraform, mas não cria instâncias. O módulo está intencionalmente sem recursos até que permissões efetivas, AMI, rede, tipo de instância e método de acesso sejam confirmados na conta Learner Lab. Depois disso, completar o módulo e habilitar `plan/apply`.

## Erros comuns

O bootstrap reporta códigos como `CANVAS_LOGIN_FAILED`, `COURSE_NOT_FOUND`, `LEARNER_LAB_NOT_FOUND`, `LAB_TIMEOUT`, `AWS_DETAILS_NOT_FOUND`, `AWS_CREDENTIALS_INVALID` e `STS_VALIDATION_FAILED`. O portal pode alterar rótulos e seletores; ajuste os nomes em `CANVAS_COURSE_NAME` e `CANVAS_LAB_LINK_TEXT` ou os seletores centralizados em `academy/`.

Não deixe recursos do Learner Lab ativos além do necessário. Trocar de conta exige atualizar `CANVAS_USERNAME` e `CANVAS_PASSWORD` no Infisical.
