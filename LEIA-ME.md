# Auto Committer

Gerador de contribuições para o GitHub com interface em HTML, CSS e
JavaScript puro, exibida em uma janela nativa do pywebview. Não abre o
navegador nem inicia um servidor HTTP próprio. O app registra mensagens
de um banco em `log.md`, cria commits e faz push pelo Git instalado.

## Instalar e executar

Requer Python 3.10 ou superior e Git instalado.

```powershell
pip install -r requirements.txt
python main.py
```

## Gerar uma contribuição

1. Em **Auto Commit**, escolha a pasta do repositório Git.
2. Escolha um banco `.txt` ou `.csv`; a primeira mensagem válida é preenchida automaticamente e você pode selecionar outra.
3. Opcionalmente, ative **Evitar mensagens repetidas** para priorizar as mensagens menos usadas no histórico de commits local. A seleção e a frequência são recalculadas antes de cada commit.
4. Confira a mensagem e confirme a ação.

Ao confirmar, o aplicativo acrescenta uma entrada datada em `log.md`
(criando o arquivo se necessário), executa `git add .`, cria o commit com
a mensagem selecionada e faz push. O conteúdo anterior do log é
preservado. Não é necessário haver alterações prévias no repositório.
O modo de evitar repetidas compara o assunto completo do commit sem diferenciar
maiúsculas/minúsculas ou espaços nas pontas. Se o histórico mudar enquanto a
confirmação estiver aberta, o aplicativo atualiza a mensagem e pede nova
confirmação. Com a opção desligada, permanece a seleção manual do banco.

## Agendamento automático

No painel abaixo da dica, marque os dias da semana, defina o intervalo em
minutos e escolha o mínimo e o máximo de commits por dia. Salve as
configurações e faça o primeiro commit manual: esse commit ativa a automação,
é contado no progresso diário quando hoje for um dia habilitado e inicia a
contagem do intervalo. O aplicativo passa a retomar o processo automaticamente
nas próximas aberturas. A automação pode ser pausada ou retomada na tela ou no
menu da bandeja.

O progresso diário fica em `gerados/estado/agendamento-automatico.json` e as
preferências ficam em `gerados/config.json`. O estado usa timestamps UTC e é
gravado atomicamente; ao voltar de uma suspensão ou reiniciar o aplicativo,
nenhum commit perdido é acumulado. O aplicativo precisa continuar em execução
(visível ou na bandeja); fechar a janela pelo X a oculta por padrão. Após três
falhas seguidas, ou se o repositório ficar indisponível, a automação pausa e
avisa o usuário. Um commit manual próximo do intervalo agendado pode ser
adiado; confirmá-lo imediatamente conta no dia e reinicia o intervalo.

## Inicialização e bandeja do Windows

Na tela **Configurações**, ative **Iniciar com o Windows** para registrar o app
na chave `Run` do usuário atual. Isso não exige administrador. O estado exibido
é lido do Registro do Windows. Quando iniciado pelo Windows, o Auto Committer
abre oculto na bandeja. **Fechar para a bandeja** fica ativado por padrão: o X
oculta a janela, mas mantém a automação. No menu do ícone, use **Abrir**,
**Pausar/Retomar commits automáticos** ou **Sair**; **Sair** encerra o processo.
Abrir o app novamente traz a janela existente para frente.

## Gráfico do GitHub

1. Crie um Personal Access Token em
   [Configurações de tokens do GitHub](https://github.com/settings/tokens).
   Para consultar contribuições públicas, não adicione permissões extras.
2. Cole o token em **Gráfico do GitHub** e conecte a conta.
3. Consulte os últimos 12 meses, escolha um ano ou informe datas
   personalizadas (até um ano por consulta).

O token fica apenas na memória da interface e é enviado diretamente ao
GitHub; não é enviado ao Python nem salvo em `localStorage` ou
`sessionStorage`. **Sair** apaga a conexão em memória. Após um commit com
push, o gráfico é atualizado; o GitHub pode levar alguns instantes para
refletir a contribuição.

## Estrutura

- `main.py`: cria a janela pywebview e conecta a API Python.
- `backend/api.py`: seleção de pasta, estado do repositório, sugestões e histórico.
- `commit_message_selector.py`: leitura do histórico Git e seleção por frequência.
- `committer.py`: operações Git reutilizadas pela API.
- `web/`: tela, estilos e integração com o GitHub.
- `windows_startup.py`, `single_instance.py` e `system_tray.py`: integração
  opcional com recursos do Windows.
- `tests/`: testes de API, seleção de mensagens, GitHub e commits.

Além do pywebview, a bandeja usa `pystray` e `Pillow` para o ícone. Não há
dependências de front-end nem servidor local.
