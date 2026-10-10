# 00 — Referências: o que os outros apps fazem e o que as plataformas permitem

Levantamento por pesquisa na web em 2026-10-09, para embasar o plano. Vale como ponto de
partida, não como verdade final:

- **(of.)** vem do fabricante ou da plataforma; **(com.)** vem de comunidade, engenharia reversa
  ou review; **(incerto)** não foi confirmado.
- As fontes estão no fim, com a marca `[S#]`. Não foram reconferidas uma a uma.
- O Reddit e os tópicos do Cloudy Nights não puderam ser lidos; a opinião de usuários vem de
  fichas de loja, fóruns e reviews.
- O que foi **medido na nossa Jetson** está em [`03-conexao.md`](03-conexao.md), não aqui.

## 1. Os apps concorrentes

Todos seguem o mesmo fluxo: ligar, acertar hora e local, conectar, escolher o alvo no atlas,
apontar com reconhecimento do céu, focar, empilhar ao vivo, rever no álbum, compartilhar. O
que os separa é o planejamento de vários alvos e noites, a ajuda de alinhamento polar e o
acabamento da imagem dentro do app.

| App | O que tem | Elogios e queixas |
|---|---|---|
| **DWARFLAB** (DWARF 3 / mini), 3,5 estrelas [S1] | Início com aparelhos próximos e conexão por app, NFC ou IP; atlas com goto de um toque; álbum; modos foto, vídeo, time-lapse, céu profundo, Via Láctea, rastro de estrelas, sistema solar [S1,S2]. Agenda (só céu profundo) e mosaico planejado no atlas [S1,S2]. Assistente de modo equatorial [S3]. Estúdio no álbum, com empilhamento no aparelho ou na nuvem [S1,S2]. Atualizar firmware exige internet e 20% de bateria, sem volta [S2,S4] | A favor: controle manual, modo avançado, agenda [S5]. Contra: congelamentos, quedas de conexão, foco [S1]; perde ajustes ao voltar uma tela (com.) [S5] |
| **Seestar** (S50 / S30), 4,2 estrelas [S6] | Abas de céu profundo, sistema solar, paisagem, Via Láctea, plano, atlas, álbum, comunidade [S6]. "Plano automático de um toque" [S6]. Mosaico, chamado de enquadramento (com.) [S7]. Modo equatorial desde 2025 [S9]. Realce da imagem no empilhamento e exportação em lote [S6] | A favor: simples para iniciante [S10]. Contra: o WiFi do aparelho não tem internet [S11]; plano em grade de 10 minutos, sem sobreposição (com.) [S7,S8]; em 2024 faltava digitar RA/DEC (com.) [S7] |
| **ASIAIR**, 3,9 estrelas [S12] | Prévia e empilhamento, foco automático, guiagem, execução automática, plano de vários alvos com mosaico, alinhamento polar, atlas com centralização por reconhecimento do céu [S12,S13]. Firmware obrigatório ao entrar na captura [S13] | A favor: alinhamento polar e reconhecimento do céu guiados (review promocional) [S15]. Contra: o app perde o aparelho com o WiFi estável, trava no iPhone [S14]; só aceita equipamento da ZWO [S15] |
| **Vaonis Singularity**, 4,1 estrelas [S16] | "Planejar a noite", mosaico, modo avançado, estúdio de cor [S16]. Plano de várias noites [S16]. Fotos por FTP no WiFi [S16,S17] | A favor: o aparelho trabalha sozinho a noite toda [S18]. Contra: só em pé no tablet; imagens do catálogo borradas [S16] |
| **Unistellar** | Visão realçada, alvos por catálogo ou coordenadas, ciência cidadã [S19]. Até dez celulares: um opera, nove assistem [S20] | Pede para desligar dados móveis e VPN [S20] |

## 2. Como eles conectam

| App | Achar o aparelho | Rede | Protocolo | Pela internet |
|---|---|---|---|---|
| DWARF 3 | lista de aparelhos próximos; conexão por app, NFC ou IP [S2]. No modelo anterior o Bluetooth enviava a senha e ligava o ponto de acesso [S21] | modos automático, ponto de acesso e estação. Em estação, no modelo anterior, o ponto de acesso desliga [S2,S4,S21] | vídeo por RTSP; arquivos por FTP (of.) [S4]. Comandos por WebSocket com protobuf (com.) [S22]. A ajuda oficial chama de "ecossistema fechado" [S4] | não encontrado |
| Seestar | aviso por UDP na rede e, se falhar, o nome `seestar.local` (com.) [S23] | ponto de acesso próprio sem internet; modo estação pelo app [S23,S24] | comandos em JSON por TCP, vídeo por RTSP (com.) [S26]. Firmware recente exige um aperto de mão cifrado, fechando a porta a terceiros (com.) [S27] | sim, pela nuvem da ZWO; exige estação e internet nos dois lados [S28] |
| ASIAIR | pelo WiFi do aparelho [S12] | ponto de acesso, estação ou cabo de rede [S29] | sem documentação pública | sim, desde a versão 3.0 [S13] |
| Vaonis | ponto de acesso próprio [S18] | estação: não encontrado | FTP para as fotos [S16] | não encontrado |
| Unistellar | ponto de acesso sem senha, Bluetooth e WiFi [S20] | estação: não encontrado | não encontrado | não encontrado |

**Padrão do mercado:** ponto de acesso próprio como modo base e estação como opção. Nenhum
documenta os dois ao mesmo tempo. A dor comum é o "WiFi sem internet": dados móveis e VPN
atrapalham a conexão [S11,S18,S20].

## 3. O que as plataformas permitem

### Página web instalada (o console atual)

| | Android (Chrome) | iPhone (Safari) |
|---|---|---|
| Por HTTP na rede local | não instala como app: exige HTTPS [S30,S31]. Fica um atalho que abre no navegador | desde o iOS 26, todo site posto na tela inicial abre como app; a fonte não exige HTTPS [S33]. Tela cheia por HTTP deve funcionar; **não testado** |
| Por HTTPS confiável | instala em janela própria [S34] | idem [S31] |

Dois avisos para o console web no iPhone: o sistema suspende o app em segundo plano e o
WebSocket morre sem avisar [S47]; e há um defeito aberto em que um WebSocket de rede local é
fechado depois de um segundo em app de tela inicial [S48]. O nosso console já volta a consultar
sozinho quando o canal cai, o que cobre os dois casos.

HTTPS numa rede sem internet tem dois caminhos, ambos com atrito: uma autoridade certificadora
própria instalada em cada celular [S37,S38,S39], ou um domínio público com certificado emitido
por desafio de DNS, respondido localmente [S40,S41,S42]. A validade desses certificados está
caindo (64 dias em 2027, 45 em 2028) [S43]. **O app nativo dispensa as duas coisas.**

### Nomes `.local`

O Android resolve `*.local` por mDNS desde o fim de 2021, mas **não com VPN ativa nem pelos
dados móveis** [S44]. Por isso a descoberta do app não pode depender só do nome
(`03-conexao.md` §2). No iPhone o suporte é nativo.

### App nativo

| Assunto | O que vale |
|---|---|
| HTTP em rede local | Android 9 ou superior bloqueia HTTP sem cifra por padrão; libera-se por domínio na configuração de segurança de rede do app [S38,S55] |
| WiFi sem internet | Android 10 ou superior tem uma API oficial para conectar a um ponto de acesso local e usar essa rede só dentro do app [S56] |
| iPhone | exige declarar o uso de rede local e os serviços Bonjour [S51]; compilar exige um Mac |
| Bluetooth | não existe no navegador do iPhone [S54]: configuração por Bluetooth só em app nativo |

### Distribuir o app

| Caminho | Custo e limites |
|---|---|
| Instalar pelo cabo (desenvolvimento) | livre; a instalação por ADB é isenta das regras novas [S57] |
| APK fora da loja | **atenção, Brasil:** a verificação de desenvolvedores do Android começa por Brasil, Indonésia, Singapura e Tailândia. Segundo a página de perguntas (jul/2026), a instalação direta "ainda não" é afetada e a regra geral fica para 2027; um anúncio anterior diz outra coisa. **(incerto) reconferir antes de distribuir** [S57,S58] |
| Conta de distribuição limitada | grátis, até 20 aparelhos, sem documento [S57] |
| Google Play | conta completa: US$ 25, uma vez [S57] |
| iPhone sem pagar | o app instalado expira em 7 dias; até 3 aparelhos [S59] |
| App Store | US$ 99 por ano [S62] |

## 4. WiFi da Jetson (fontes externas)

- A placa do kit usa o chip Realtek RTL8822CE [S64]. Perguntada sobre roteador e ponto de
  acesso ao mesmo tempo, a NVIDIA respondeu que "por padrão não está habilitado" [S65]. **A
  nossa medição confirma** (`03-conexao.md` §1.1).
- O driver do próprio kernel (rtw88) só declara "uma estação mais um ponto de acesso, num
  canal só" para esse chip a partir do Linux 6.4; não existe no 5.15 do JetPack 6 [S66]. O
  JetPack 7.2 traz o kernel 6.8 [S69], mas os relatos mostram o driver do fabricante em uso
  também nele [S67,S68]. É um caminho possível no futuro, **(incerto)**.
- Adaptadores USB com bom suporte a ponto de acesso no Linux: os de chip **MT7612U** são os
  mais citados, com driver no kernel desde a versão 4.19 e a combinação estação + ponto de
  acesso declarada no 5.15 [S73,S74]. Os de chip MT7921AU pedem kernel mais novo [S74].

## 5. O que isso muda no nosso plano

1. **Rede como a do mercado:** ponto de acesso próprio no campo, estação em casa, troca
   automática. Ninguém entrega os dois juntos; não é requisito.
2. **Descoberta em camadas:** nome na rede, serviço anunciado e, como o Seestar, um aviso por
   UDP para quando o mDNS falhar (VPN, dados móveis).
3. **App nativo se justifica:** resolve o WiFi sem internet, dispensa HTTPS com certificado no
   celular e permite Bluetooth. O Flutter cobre tudo isso com código nativo pontual.
4. **Paridade mínima:** atlas com goto de um toque, plano de vários alvos e noites com mosaico,
   ajuda de alinhamento polar, foco automático, empilhamento com ajustes, álbum com acabamento
   e exportação, compartilhar. Tudo já está em `01-funcionalidades.md`.
5. **Onde podemos ser melhores sem muito custo:**
   - **API aberta e documentada** — o DWARF se declara fechado e a ZWO passou a cifrar a porta
     de comandos;
   - **tudo sem internet**, inclusive atualizar firmware (o DWARF exige internet);
   - **RA/DEC à mão e plano sem grade fixa** (queixas do Seestar);
   - **não perder ajustes ao trocar de tela** e **dizer a verdade sobre a conexão** (queixas do
     DWARF e do ASIAIR).
6. **Vários celulares, um operador:** o modelo do Unistellar confirma a ideia de um comandar e
   os outros assistirem.
7. **Distribuição:** conferir a regra de verificação de desenvolvedores do Android antes de
   entregar o APK a outras pessoas no Brasil.

## Fontes

- S1: https://apps.apple.com/app/id1667394131
- S2: https://help.dwarflab.com/en/docs/DWARF-3-Smart-Telescope-User-Manual-Part1-App-Interface-Introduction?product=dwarf-3
- S3: https://help.dwarflab.com/en/docs/How-to-Set-up-DWARF-3-for-EQ-mode-in-the-South-Hemisphere
- S4: https://help.dwarflab.com/en/docs/Trouble-Shooting-Guide-For-DWARF-3-Users
- S5: https://skiesandscopes.com/seestar-s50-vs-dwarf-3/
- S6: https://apps.apple.com/app/id6447429891
- S7: https://britastro.org/forums/topic/seestar-s50-self-help-group/page/2
- S8: https://eu.seestar.com/blogs/seestar-guide/seestar-auto-plan
- S9: https://agenaastro.com/articles/guides/how-to-set-up-and-use-eq-mode-on-the-zwo-seestar-s50-s30
- S10: https://www.livescience.com/products/optics/zwo-seestar-s50-pro-smart-telescope-review
- S11: https://eu.seestar.com/blogs/tutorial/access-the-internet-while-filming
- S12: https://apps.apple.com/us/app/asiair/id1367782034
- S13: https://www.zwoastro.com/?p=93119
- S14: https://bbs.zwoastro.com/d/22635-asiair-v233-has-been-released ; https://stargazerslounge.com/topic/370905-asiair-driving-me-bonkers
- S15: https://app.astrobin.com/forum/topic/133324/switching-from-osc-to-mono-asiair-vs-nina
- S16: https://apps.apple.com/app/id1515280835
- S17: https://support.vaonis.com/portal/en/kb/faq/product-app-support/singularity-by-vaonis/updates
- S18: https://space.com/vaonis-vespera-ii-smart-telescope-review ; https://www.astronomy.com/observing/vaonis-new-smart-scope-reviewed/
- S19: https://www.skyatnightmagazine.com/reviews/telescopes/unistellar-evscope-review/
- S20: https://help.unistellar.com/hc/en-us/articles/360007869100-How-do-I-control-my-eVscope-WiFi-or-Bluetooth-
- S21: https://help.dwarflab.com/docs/How-to-Deal-With-Connection-Problems-for-DWARF-II
- S22: https://github.com/stevejcl/dwarf_python_api
- S23: https://seestarpy.readthedocs.io/en/stable/examples/basic_connection.html
- S24: https://us.seestar.com/blogs/tutorial/transfer-files-using-wi-fi
- S26: https://seestarpy.readthedocs.io/en/stable/info/image_stream_protocol.html
- S27: https://seestarpy.readthedocs.io/en/stable/info/authentication.html
- S28: https://us.seestar.com/blogs/tutorial/seestar-new-feature-telescope-network-remote-function-user-guide
- S29: https://us.zwoastro.com/blogs/usage-tutorials/asiair-guide-four-ways-to-connect-the-asiair-pro-to-network-updated
- S30: https://web.dev/articles/install-criteria
- S31: https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Installable_PWAs
- S33: https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/
- S34: https://moodeaudio.org/forum/showthread.php?pid=60715
- S37: https://github.com/FiloSottile/mkcert
- S38: https://developer.android.com/privacy-and-security/security-config
- S39: https://support.apple.com/en-us/103769
- S40: https://community.letsencrypt.org/t/using-lets-encrypt-for-local-network-devices/101256
- S41: https://notthebe.ee/blog/easy-ssl-in-homelab-dns01
- S42: https://forums.plex.tv/t/dns-rebinding-issue/357676
- S43: https://isrg.org/post/from-90-to-45/
- S44: https://source.android.com/docs/core/architecture/modular-system/dns-resolver
- S47: https://bugs.webkit.org/show_bug.cgi?id=200255
- S48: https://developer.apple.com/forums/thread/811063
- S51: https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
- S54: https://apps.apple.com/app/id1492822055
- S55: https://forum.ionicframework.com/t/ionic-4-android-9-cleartext-http-not-permitted-error/172999
- S56: https://developer.android.com/develop/connectivity/wifi/wifi-bootstrap
- S57: https://developer.android.com/developer-verification/guides/faq
- S58: https://android-developers.googleblog.com/2026/03/android-developer-verification-rolling-out-to-all-developers.html
- S59: https://developer.apple.com/support/compare-memberships/
- S62: https://developer.apple.com/programs/enroll/
- S64: https://www.waveshare.com/product/iot-communication/wireless-aw-cb375nf.htm
- S65: https://forums.developer.nvidia.com/t/can-jetson-orin-nano-super-modify-wifi-mode-to-connect-to-a-network-and-host-a-hotspot-simultaneously-wifi-sta-ap/357660
- S66: https://raw.githubusercontent.com/torvalds/linux/v6.4/drivers/net/wireless/realtek/rtw88/main.c
- S67: https://forums.developer.nvidia.com/t/jetson-orin-nano-no-wifi/296609
- S68: https://forums.developer.nvidia.com/t/my-experience-with-wifi-adapters-on-orin-nano-rtl8822ce-vs-qcnfa765/381849
- S69: https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2.1.md
- S73: https://raw.githubusercontent.com/torvalds/linux/v5.15/drivers/net/wireless/mediatek/mt76/mt76x02_util.c
- S74: https://github.com/morrownr/USB-WiFi/blob/main/home/USB_WiFi_Adapters_that_are_supported_with_Linux_in-kernel_drivers.md
