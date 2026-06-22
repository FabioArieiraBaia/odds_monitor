# Manual do Usuário - Odds Divergence Monitor

Bem-vindo ao **Odds Divergence Monitor**! Este sistema foi projetado para cruzar e analisar dados em tempo real entre a Bet365 e a BetBurger, com o objetivo de encontrar **Atrasos de Placar (Courtsiding)** e oportunidades únicas no mercado Ao Vivo.

---

## 1. Instalação e Inicialização
1. Dê um duplo clique no arquivo de instalação (`Odds Divergence Monitor Setup.exe`).
2. O sistema será instalado no seu computador e criará um ícone na área de trabalho.
3. Ao abrir o aplicativo, uma janela principal será carregada exibindo o painel (Dashboard).
4. **Importante:** Nos bastidores, o sistema abrirá automaticamente abas ocultas ou visíveis do navegador Google Chrome para realizar a varredura das odds na Bet365 e BetBurger. Não feche essas abas se elas aparecerem, pois elas são os "olhos" do robô!

---

## 2. Como Funciona?
A ferramenta funciona capturando o placar (Set, Game e Pontos) e o tempo de jogo de centenas de partidas diretamente da tela da Bet365 e cruzando esses mesmos dados com as informações super-rápidas da BetBurger.
* Se a BetBurger indicar que um time marcou um ponto (ex: `15:40`), mas a tela da Bet365 ainda estiver presa no passado (ex: `15:30`), o sistema detecta a "Divergência" e emite um alerta na sua tela!
* Com esse alerta, você tem uma pequena janela de tempo para apostar no próximo ponto ou no vencedor do set na Bet365 **antes** que eles percebam o que aconteceu na vida real.

---

## 3. Configurações da Conta BetBurger (Fundamental)
Para que o sistema consiga extrair centenas de partidas em tempo real sem limite de lucro e sem os atrasos artificiais de 15 minutos impostos às contas gratuitas, **você precisa configurar sua conta Live Pro**.

1. Na tela inicial do aplicativo, localize a seção **"⚙️ Configurações (BetBurger)"**.
2. Clique para expandir o painel.
3. Insira o seu E-mail e a Senha da sua conta BetBurger (precisa ser uma conta com plano Premium/Pro ativo).
4. Clique em **Salvar Credenciais**.
5. **Atenção:** Após salvar, feche o aplicativo e abra-o novamente para que o robô faça o login automático na BetBurger utilizando as novas credenciais inseridas.

---

## 4. O Painel de Alertas
Toda vez que uma divergência for encontrada, a tela brilhará (Flash) e um som de notificação será emitido.
* **Painel Central:** Exibe o esporte, os nomes dos times e a comparação lado a lado do placar. A métrica divergente ficará destacada em Vermelho vs Verde.
* **Mutar Som:** No canto superior direito, existe um botão de sino (🔔). Clique nele para silenciar os alertas sonoros caso deseje apenas o alerta visual.
* **Links Diretos:** Ao lado direito de cada partida, existem botões para abrir as partidas diretamente na Bet365 e na BetBurger com um clique.

---

## 5. Monitoramento de Links Personalizados
Se você encontrou uma partida interessante ou quer acompanhar uma liga específica que o robô não está puxando na tela principal:
1. Copie o link direto da partida na Bet365.
2. Abra a seção **"🔗 Links Personalizados"** no aplicativo.
3. Cole o link no campo de texto e clique em **+ Adicionar**.
4. O robô vai fixar a atenção naquela partida e alertar imediatamente sobre qualquer movimentação anormal detectada em relação aos radares externos.

---

## 6. Solução de Problemas Comuns
* **O Status fica apenas como "Desconectado":** Verifique sua conexão de internet e certifique-se de não estar usando VPNs agressivas que bloqueiem o tráfego do WebSocket (porta 8000).
* **Nenhum alerta aparece:** Verifique se há jogos Ao Vivo ocorrendo nos esportes rastreados no momento atual. Certifique-se também de que o login da BetBurger foi inserido corretamente.
* **O sistema acusa erro "ENOENT python":** Ocasionalmente o antivírus pode bloquear a inicialização dos binários embutidos. Adicione a pasta do aplicativo nas exceções do seu Windows Defender.
