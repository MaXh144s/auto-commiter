# Auto Committer

Aplicativo desktop para registrar mensagens em um repositório Git, criar commits
e enviá-los ao GitHub. Também oferece agendamento local de commits e um gráfico
de contribuições do GitHub.

A interface é construída em HTML, CSS e JavaScript e executada em uma janela
nativa com [pywebview](https://pywebview.flowrl.com/). O Python cuida das
operações locais e do Git. O aplicativo não inicia um servidor HTTP próprio e
não abre a interface em um navegador externo.

## Funcionalidades

- Seleção de repositório Git e banco de mensagens em `.txt` ou `.csv`.
- Criação de commits com confirmação, histórico de ações e envio ao remoto.
- Opção para priorizar mensagens menos usadas no histórico local.
- Agendamento diário configurável por dia da semana, intervalo e quantidade
  mínima e máxima de commits.
- Persistência local das configurações e do progresso do agendamento.
- Bandeja do sistema, instância única e inicialização com o Windows.
- Gráfico de contribuições do GitHub com calendário e estatísticas.

## Requisitos

- Windows 10 ou posterior para a bandeja e a integração com o arranque do
  Windows.
- Python 3.10 ou posterior para executar a partir do código-fonte.
- Git instalado e disponível no `PATH`.
- Um repositório Git com remoto configurado e autenticação de push funcional.
- Microsoft Edge WebView2 Runtime para a janela nativa no Windows.

## Executar a partir do código-fonte

No PowerShell, a partir da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Para ativar a bandeja e iniciar com o Windows, execute o aplicativo em Windows.
O modo fonte pode ser usado sem compilar o executável.

## Criar commits

1. Em **Auto Commit**, selecione a pasta do repositório Git.
2. Escolha um banco `.txt` ou `.csv`. Use uma mensagem por linha; o formato
   recomendado é `tipo: mensagem`, por exemplo:

   ```text
   feat: adiciona validação do formulário
   fix: corrige erro de paginação
   docs: atualiza instruções de instalação
   ```

   Mensagens sem um tipo reconhecido são tratadas como `chore`.
3. Confira a mensagem e confirme o commit.

O aplicativo adiciona uma entrada datada a `log.md` na raiz do repositório,
preservando o conteúdo existente. Em seguida, executa `git add .`, cria o
commit e tenta enviá-lo ao remoto. Portanto, `git add .` inclui todas as
alterações e arquivos não rastreados presentes no repositório selecionado.
Configure o Git e a autenticação do remoto antes de usar o envio.

Com **Evitar mensagens repetidas** ativado, o aplicativo consulta os assuntos
dos commits locais, compara as mensagens sem diferenciar maiúsculas/minúsculas
ou espaços nas extremidades e prioriza as menos usadas. A contagem é refeita
antes de cada commit.

## Agendamento automático

Na tela **Auto Commit**, configure os dias ativos, o intervalo mínimo entre
commits e os limites diário mínimo e máximo. Salve as opções e faça um commit
manual bem-sucedido para ativar a automação. O banco precisa conter pelo menos
duas mensagens distintas para que a automação seja ativada.

O agendador escolhe um alvo diário dentro dos limites definidos, respeita os
dias e o intervalo configurados e escolhe novamente uma mensagem antes de cada
commit. O progresso do dia é persistido; commits perdidos enquanto o app estava
fechado ou o computador desligado não são acumulados.

**O agendamento só funciona enquanto o aplicativo estiver em execução.** Fechar
a janela pelo X a oculta na bandeja por padrão. Use **Sair** no menu da bandeja
para encerrar o processo. Se o repositório deixar de estar disponível ou
ocorrerem três falhas consecutivas, a automação é pausada e o app informa o
problema.

### Iniciar com o Windows

Na tela **Configurações**, ative **Iniciar com o Windows** para registrar o
aplicativo na chave `Run` do usuário atual. Não é necessário acesso de
administrador. Ao entrar na sessão do Windows, o aplicativo abre oculto na
bandeja e tenta retomar o agendamento persistido.

Essa opção não transforma o aplicativo em serviço: é necessário que o Windows
esteja ligado e que a sessão do usuário tenha sido iniciada. Se o computador
estiver desligado, nenhum commit será feito nesse período.

## Gráfico de contribuições do GitHub

1. Crie um Personal Access Token nas
   [configurações de tokens do GitHub](https://github.com/settings/tokens).
   Para consultar contribuições públicas, não conceda permissões adicionais.
2. Na tela **Gráfico do GitHub**, cole o token e conecte a conta.
3. Consulte o último ano, escolha outro ano ou informe um período personalizado
   de até um ano.

O token é mantido somente na memória da interface e enviado diretamente às APIs
do GitHub. Ele não é enviado à API Python do aplicativo nem gravado em
`localStorage` ou `sessionStorage`. Ao fechar o app, será necessário conectar-se
novamente. Use **Sair** para apagar a conexão da memória da interface.

## Configuração e privacidade dos dados

As configurações e o estado do agendamento são salvos localmente em `gerados/`.
Ao executar o `.exe`, essa pasta fica ao lado do executável, por exemplo,
`dist/gerados/`. Preserve essa pasta ao atualizar o executável: ela contém o
caminho do repositório, o banco de mensagens e o progresso diário. Ela é
ignorada pelo Git para evitar publicar dados locais.

O token do GitHub não é persistido. O gráfico requer uma conexão à internet;
o Git local e o push dependem da configuração do Git e do remoto do usuário.

## Testes

Execute a suíte padrão da biblioteca `unittest`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Gerar o executável para Windows

Instale o PyInstaller no ambiente virtual e gere o executável usando a
configuração do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm .\AutoCommitter.spec
```

O resultado é `dist/AutoCommitter.exe`. Para atualizar uma instalação, encerre
o app pelo menu da bandeja, substitua o executável e mantenha a pasta `gerados`
existente. Se o executável for movido para outro caminho, desative e reative
**Iniciar com o Windows** para atualizar o caminho registrado.

## Estrutura do projeto

```text
backend/                   API Python exposta à interface
tests/                     Testes automatizados
web/                       HTML, CSS e JavaScript da interface
automatic_scheduler.py     Lógica do agendador
committer.py               Operações Git e criação de commits
commit_message_selector.py Comparação e seleção de mensagens
config.py                  Configurações e dados locais
main.py                    Inicialização da janela nativa
scheduler_state.py         Persistência do estado do agendador
single_instance.py         Controle de instância única no Windows
system_tray.py             Bandeja do sistema
windows_startup.py         Integração com o arranque do Windows
AutoCommitter.spec         Configuração do PyInstaller
requirements.txt           Dependências da aplicação
```

## Dependências

As dependências da aplicação estão listadas em `requirements.txt`:

- `pywebview`: janela nativa e ponte entre JavaScript e Python.
- `pystray`: ícone e menu da bandeja do sistema.
- `Pillow`: geração da imagem do ícone da bandeja.

O PyInstaller é necessário somente para gerar o executável.
