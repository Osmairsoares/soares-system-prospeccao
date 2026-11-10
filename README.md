# Soares System — hospedagem no Render

## Publicar sem instalar nada no computador

1. Entre em https://github.com e crie uma conta, se necessário.
2. Clique em **New repository**, dê o nome `soares-system-prospeccao` e selecione **Private** (se desejar).
3. No repositório, escolha **Add file > Upload files** e envie **os três arquivos** desta pasta: `Soares_System.html`, `server.py` e `render.yaml` (não envie somente o ZIP). Clique em **Commit changes**.
4. Entre em https://dashboard.render.com e conecte sua conta do GitHub.
5. Clique em **New > Blueprint** (ou a opção equivalente de Blueprint no painel), selecione o repositório e autorize a leitura. Confirme a criação do serviço definido em `render.yaml`.
6. Aguarde o deploy e abra a URL HTTPS que o Render fornecer, normalmente `https://soares-system-prospeccao.onrender.com` (o endereço final pode ser diferente).
7. Adicione uma cidade, selecione o tipo de estabelecimento e clique em **Buscar clientes**. Teste primeiro com Osasco — SP.

## Importante

- O Render pode mudar os nomes de botões e a disponibilidade dos planos. Confira as opções e preços no painel **antes de confirmar**. Não é necessário instalar Python ou programas no computador.
- O servidor de busca roda no Render; **não** é preciso manter seu computador ligado.
- A busca usa serviços comunitários do OpenStreetMap/Overpass/Photon/Nominatim. **Não há garantia de disponibilidade, volume, cobertura ou contatos comerciais**. A hospedagem não corrige indisponibilidade dos serviços externos.
- A API `/api/proxy` é limitada a destinos predefinidos e tem limite de chamadas por IP, mas não possui autenticação. Evite divulgar amplamente o link sem acrescentar login e controles de uso.
- **Os clientes e as tarefas são salvos apenas no localStorage do navegador**, não no Render. Não são sincronizados entre computadores. Use **Exportar Excel** e **Configurações > Exportar backup JSON** regularmente. A hospedagem gratuita pode dormir após inatividade, causando espera na primeira abertura.
- O menu, CRM, cadastro manual, importação e exportação CSV permanecem na interface. Telefones/e-mails só aparecem se estiverem nos dados públicos.
- Para uso comercial frequente, considere uma API de dados com contrato de uso e banco de dados, respeitando LGPD e licenças dos provedores.

## Diagnóstico

Abra `https://SEU-ENDERECO.onrender.com/health`: deve aparecer `{"ok": true, ...}`. Isso verifica o servidor, **não** a disponibilidade dos dados externos. Se a busca falhar, copie a mensagem de erro mostrada no painel. Verifique **Logs** do serviço no Render.
