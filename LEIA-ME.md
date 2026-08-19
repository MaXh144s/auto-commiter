# Auto Committer

Programa que roda em segundo plano (bandeja do sistema) e faz commits
automáticos em repositórios git configurados por você, em horários
espalhados de forma não robótica.

⚠️ **Nota honesta:** isso enche o gráfico de contribuições do GitHub,
mas não representa trabalho de verdade. É só estética.

---

## 1. Instalar dependências

Com Python 3.10+ instalado no Windows, abra o terminal na pasta do
projeto e rode:

```
pip install -r requirements.txt
```

## 2. Rodar direto com Python (pra testar)

```
python main.py
```

Isso abre a janela de configuração na hora (porque não foi chamado com
`--silencioso`). Configure um trabalho:

1. Aba **Trabalhos** → **+ Novo**
2. Preencha:
   - **Pasta do repositório git**: a pasta local do seu repositório (precisa ter `.git`)
   - **Arquivo alvo**: nome do arquivo que vai ser alterado a cada commit (ex: `log.md`)
   - **O que commitar**: `mensagens` (usa o banco de frases), `linha_data` (só data/hora) ou `comando_custom` (roda um comando seu)
   - **Banco de mensagens**: importe o `exemplo_mensagens.txt` incluso, ou crie o seu (.txt = uma frase por linha, .csv = primeira coluna)
   - Dias da semana, janela de horário, quantidade de commits por dia, intervalo mínimo entre eles e chance de pular o dia (esse é o "anti-spam")
3. Clique em **💾 Salvar trabalho**
4. Use **▶ Rodar agora** pra testar um commit imediatamente

Na aba **Configurações gerais**, marque "Iniciar automaticamente com o
Windows" e salve — isso cria um atalho na pasta de Inicialização do
Windows.

## 3. Gerar o executável (.exe)

Pra não depender de abrir terminal, gere um `.exe` único:

```
pyinstaller --noconfirm --onefile --windowed --name AutoCommitter main.py
```

O executável fica em `dist/AutoCommitter.exe`. Copie essa pasta
inteira (`dist`) pra onde quiser manter o programa — ele salva a
configuração (`config.json`) e o histórico ao lado do executável.

- `--windowed`: não abre janela de console (console preto) junto
- `--onefile`: gera um único .exe

## 4. Como o "não abrir toda vez" funciona

- Quando o Windows liga, o atalho criado na pasta de Inicialização
  chama o programa com `--silencioso` → ele sobe só na bandeja, sem
  janela nenhuma.
- Se você (usuário) abrir o `AutoCommitter.exe` de novo manualmente,
  o programa detecta que já tem uma instância rodando (via uma
  verificação de porta local) e manda essa instância existente abrir
  a janela de configuração — sem duplicar o ícone na bandeja.

## 5. Algoritmo anti-spam (como evita ficar óbvio demais)

Para cada trabalho, todo dia o programa decide:

1. Se hoje é um dos dias da semana ativos.
2. Se, por sorte (`chance de pular o dia`), hoje simplesmente não
   haverá nenhum commit.
3. Quantos commits vão rolar hoje (número aleatório entre o mínimo e
   o máximo configurados).
4. Em que horários exatos, dentro da janela configurada, respeitando
   sempre o intervalo mínimo entre um commit e outro.

Essa agenda é recalculada uma vez por dia — os horários nunca se
repetem de um dia pro outro.

## 6. Estrutura de arquivos

```
auto-committer/
├── main.py          → inicialização, bandeja, instância única
├── gui.py            → janela de configuração
├── scheduler.py       → algoritmo anti-spam + loop em background
├── committer.py       → executa de fato o git add/commit/push
├── config.py          → leitura/escrita de config.json e estado
├── startup.py          → cria/remove atalho de inicialização do Windows
├── config.json         → (gerado automaticamente) seus trabalhos configurados
├── estado/               → (gerado automaticamente) progresso do banco de mensagens por trabalho
└── exemplo_mensagens.txt → banco de frases de exemplo
```
