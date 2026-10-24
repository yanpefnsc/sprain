# Monitoramento externo de disponibilidade

A API já expõe `/api/v1/health/readiness`. Esse endpoint responde 503 se o
banco, a extensão PostGIS, as tabelas essenciais ou a malha estiverem
indisponíveis. O script `scripts/monitorar_disponibilidade.py` confere a
resposta HTTP e os campos `status=READY`, `postgis=OPERACIONAL` e
`total_trechos_osm>0`.

Execute o monitor **fora do servidor da API**. Um monitor no mesmo servidor
também cai quando o host ou a rede cai. Requer Python 3.9+, uma URL pública
HTTPS para readiness e um webhook do Discord criado para a equipe. O endpoint
não precisa de chave de API; não inclua token na URL. Guarde o webhook apenas
em `/etc/sprain/monitor.env` na máquina de monitoramento, com permissão 0600.

Exemplo de conteúdo (preencher fora do Git):

```ini
SPRAIN_HEALTH_URL=https://DOMINIO_DO_PILOTO/api/v1/health/readiness
SPRAIN_DISCORD_WEBHOOK=https://discord.com/api/webhooks/ID/TOKEN
```

Copie `deploy/systemd/sprain-monitor.service` e `.timer` para
`/etc/systemd/system/` nessa **outra máquina**, com uma cópia do script em
`/opt/sprain/scripts/`. Após testar manualmente, execute `systemctl
daemon-reload` e `systemctl enable --now sprain-monitor.timer`. Consulte
`systemctl status sprain-monitor.timer` e `journalctl -u sprain-monitor.service`.
O serviço guarda apenas contagem de falhas e estado do alerta em
`/var/lib/sprain-monitor/state.json`; não grava o webhook ali.

O monitor avisa no Discord após duas falhas consecutivas e envia um aviso de
recuperação quando readiness volta. Ele não repete o mesmo alerta em cada
minuto. Falha ao enviar o webhook mantém o alerta pendente para nova tentativa.
Um teste local com servidor HTTP simulado confirmou: duas respostas 503 geram
um aviso; a recuperação gera outro; sondas posteriores não duplicam mensagens.
HTTP só é aceito com `--allow-http-local-test` e endereço loopback.

Antes de considerar a etapa concluída no piloto, configure a URL real e o
webhook, simule uma indisponibilidade controlada no ambiente de homologação e
confirme o recebimento pela equipe. Este monitor não acompanha atraso do worker,
idade dos dados externos, espaço em disco nem sucesso do backup; esses sinais
precisam de alertas próprios.
