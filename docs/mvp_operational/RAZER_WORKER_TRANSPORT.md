# SAFE-FIELD — transporte privado Raspberry Pi → Razer

## Estado

`IMPLEMENTADO E TESTADO EM LOOPBACK / NÃO INSTALADO`

Esta extensão é aditiva. Ela não altera RTL, FPGA, transporte PCM, captura,
segmentação, histórico ou artefatos do TP4. O Raspberry Pi continua sendo o
dono da ocorrência e dos arquivos originais. O Razer funciona apenas como
worker local para inferência pesada sobre um segmento fechado.

## Limite de confiança e privacidade

O worker aceita somente duas classes de entrada:

1. um WAV de segmento, seu identificador e hashes, retornando ASR, turnos
   diarizados e um embedding para cada turno;
2. uma transcrição já atribuída a `SPEAKER_nn`, retornando raciocínio
   fundamentado (`facts`, `hypotheses`, papéis provisórios, contradições e
   lacunas de informação).

O protocolo rejeita recursivamente chaves que indiquem `DIAO`, PDF,
`knowledge`, `guidance`, `occurrence` ou `history`. Ele nunca oferece um
`KnowledgeProvider`. O helper `remote_pipeline_providers(client, knowledge)`
injeta o `KnowledgeProvider` recebido diretamente na pipeline do Pi; portanto,
a recuperação DIAO continua no Core e somente depois da confirmação humana.
O ID de ocorrência não é enviado para raciocínio: o cliente deriva um
`SCOPE_<HMAC>` opaco usando um segredo exclusivo do Pi, que não é o bearer
token conhecido pelo worker. Sem configuração, esse segredo é aleatório por
processo; para continuidade após restart, pode ser injetado por variável local.

ASR e speaker inference usam a mesma requisição, com durabilidade em duas
fases. Se ASR termina e diarização/embedding falha, a resposta traz
`processing_status=PROCESSING_PENDING`, o ASR concluído e nenhum turno parcial.
O proxy deixa a pipeline persistir a transcrição e só então levanta
`ProviderUnavailable` na chamada de diarização. A resposta parcial não é
memorizada como sucesso e sai do cache cliente após consumo, permitindo retry.

Este desenho não autoriza qualquer API de IA em nuvem. O cliente aceita apenas
`localhost` ou endereço IP literal privado. Nomes DNS e IPs públicos falham
fechados. Em non-loopback, HTTPS é obrigatório por padrão: bearer token não
cifra áudio nem credencial. HTTP direto na LAN só é possível com a flag de
risco explícita `allow_insecure_private_http=True` nos dois lados.

## Protocolo v1

- Nome: `safe-field-razer-worker`
- Versão: `1`
- Transporte: JSON UTF-8 sobre HTTP POST
- Análise de segmento: `POST /v1/inference/segment`
- Raciocínio: `POST /v1/inference/reasoning`
- Saúde: `GET /v1/health`
- Conteúdo do áudio: WAV em Base64 (`audio/wav;base64`)

Toda requisição possui:

- `request_id` determinístico sobre caminho + operação + payload;
- `operation`;
- `input_sha256`, calculado sobre o payload canônico;
- payload estritamente validado.

Toda resposta bem-sucedida ecoa:

- `request_id`, operação e versão;
- SHA-256 do corpo exato da requisição;
- SHA-256 do payload de entrada;
- SHA-256 do resultado;
- `worker_id`, horário UTC e classes exatas dos providers usados.

O cliente recalcula e compara os três hashes. Resposta truncada, adulterada,
fora de versão ou com proveniência ausente vira `ProviderUnavailable`.

## Idempotência

O worker mantém um cache LRU limitado por `request_id` durante a vida do
processo. Repetir o mesmo ID e corpo devolve exatamente a resposta já produzida
e não repete inferência. Reutilizar o ID com outro corpo retorna HTTP 409. Uma
falha transitória libera a reserva para retry; ela não é memorizada como
sucesso. Após reinício do processo, a pipeline do Core continua sendo a fonte
durável dos jobs, e os providers/raciocínio também devem manter IDs de saída
determinísticos.

O cliente também limita seu cache de respostas por segmento a 128 entradas por
padrão (`segment_cache_capacity`), evitando crescimento ilimitado durante uma
ocorrência longa.

Se todas as vagas idempotentes estiverem `pending`, uma nova chave recebe 503
em vez de ultrapassar a capacidade. Uma entrada completa pode ser evictada
mesmo quando a entrada mais antiga ainda está executando.

## Segurança implementada

- bearer token obrigatório quando o bind ou destino não é loopback;
- bind restrito a loopback ou IP privado literal; wildcard e IP público são
  recusados;
- token comparado como digest SHA-256 de tamanho fixo com
  `hmac.compare_digest`;
- redirects HTTP recusados; `Authorization` nunca é encaminhado a outro origin;
- proxies HTTP herdados do ambiente são desativados para impedir que áudio e
  bearer saiam da conexão privada direta;
- token somente em variável `SAFE_FIELD_RAZER_WORKER_TOKEN`;
- nenhum token/transcrição escrito em log; o WAV usa arquivo temporário local,
  removido após sucesso e retido com hash no nome somente no caso de timeout;
- `Content-Length` obrigatório e `Transfer-Encoding` recusado;
- limite padrão do WAV: 8 MiB;
- limite padrão da requisição: 12 MiB;
- limite padrão da resposta: 4 MiB;
- timeout configurável tanto no cliente quanto em cada provider do worker;
- validação de WAV não vazio, IDs, intervalos, confiança, vetores finitos e
  cardinalidades;
- respostas com `Cache-Control: no-store` e `nosniff`;
- erros internos são sanitizados e não expõem transcrições ou caminhos.

Um timeout de coroutine não consegue matar à força uma thread nativa criada por
um provider. Por isso, se o timeout ocorrer durante WAV→inferência, o worker
retém a cópia temporária `safe_field_worker_<hash>_*` em vez de apagá-la sob
uma thread ainda viva. O WAV durável no Pi permanece intacto. A implantação
usa TTL padrão de 24 h, mas o cleanup remove apenas spools expirados cujo
PID/instância proprietária já terminou. A varredura ocorre na criação e a cada
requisição. Owner atual, PID vivo, marker inválido ou liveness ambígua são
preservados conservadoramente. Consequentemente, um spool de timeout do worker
atual só fica elegível depois que esse processo termina/reinicia, mesmo se a
thread já tiver acabado; esse vazamento temporário é o risco residual escolhido
para nunca apagar áudio ainda em uso. Os diretórios podem conter áudio sensível.

Um firewall do Razer deve limitar a porta ao IP da Raspberry. Isso é uma ação
de implantação futura, não executada por esta entrega.

## Integração no Raspberry Pi

O launcher `raspberry/safe_field_core/safe_field_operational_server.py` integra
o modo remoto opcional. `local` continua sendo o default; `razer` precisa ser
selecionado por `--ai-mode razer` ou `SAFE_FIELD_AI_MODE=razer`. A composição
não abre rede no startup e sua readiness contém estados, nunca URL/token/scope.

Configuração equivalente usando diretamente os providers:

```python
import os

from mvp.operational_intelligence.razer_worker_transport import (
    RazerWorkerClient,
    remote_pipeline_providers,
)

client = RazerWorkerClient(
    os.environ["SAFE_FIELD_RAZER_WORKER_URL"],
    bearer_token=os.environ["SAFE_FIELD_RAZER_WORKER_TOKEN"],
    scope_secret=os.environ["SAFE_FIELD_RAZER_SCOPE_SECRET"],  # somente no Pi
    timeout_seconds=90,
)
providers = remote_pipeline_providers(client, knowledge=diao_provider_local_do_pi)
```

Os proxies implementam diretamente `ASRProvider`, `DiarizationProvider`,
`SpeakerEmbeddingProvider` e `ReasoningProvider`. ASR, diarização e embeddings
compartilham uma única resposta verificada por WAV. O registro/re-ID de
`SPEAKER_nn`, persistência, grafo de fatos, confirmação e DIAO continuam no Pi.
O launcher instancia `MVPAsyncDIAOKnowledgeProvider` localmente e entrega essa
mesma instância ao helper remoto; não existe rota de knowledge no worker.

## Inicialização manual no Razer (não executada)

O launcher não instala serviço nem persiste segredo. Ele usa os caminhos de
modelos locais já reconhecidos pelo runtime. A configuração preferencial liga
o worker apenas ao loopback e põe um reverse proxy TLS autenticado na LAN:

```powershell
$env:SAFE_FIELD_RAZER_WORKER_TOKEN = Read-Host -MaskInput
$env:SAFE_FIELD_ASR_MODEL = "C:\caminho-local\asr"
$env:SAFE_FIELD_DIARIZATION_MODEL = "C:\caminho-local\diarization"
$env:SAFE_FIELD_EMBEDDING_MODEL = "C:\caminho-local\embedding"
python -m mvp.razer_worker_service --bind 127.0.0.1 --port 8766 --device cpu `
  --spool-root C:\safe-field-private-spool --spool-ttl-hours 24
```

CPU é o default porque esse é o runtime efetivamente validado. `--device cuda`
só deve ser selecionado após instalar e revalidar as DLLs CUDA exigidas pelo
CTranslate2; a GPU detectada nesta máquina ainda falha por ausência de
`cublas64_12.dll`.

Para um teste isolado em LAN confiável sem TLS, é necessário declarar o risco
explicitamente no launcher com `--allow-insecure-private-http` e no cliente com
`allow_insecure_private_http=True`. Essa opção envia áudio e bearer token sem
cifragem e não é a configuração recomendada.

Não se deve colocar valores reais em scripts, documentação, shell history ou
Git. O servidor pode ser construído diretamente com
`make_razer_worker_server(...)` quando a aplicação quiser fornecer providers
alternativos que respeitem os mesmos contratos.

## Semântica de falha

Falhas de rede, timeout, HTTP, autenticação, versão, hash ou provider são
convertidas pelos proxies em `ProviderUnavailable`. A
`AsyncSegmentPipeline` já trata essa exceção como falha recuperável:

- o WAV original permanece intocado;
- o sidecar e o job ficam em `PROCESSING_PENDING`;
- nenhuma orientação DIAO é emitida;
- um retry pode processar o mesmo artefato posteriormente.

Captura e segmentação não aguardam a rede nem a inferência.

## Testes automatizados

Comando executado:

```powershell
& .\mvp\evidence\local_ai_venv\Scripts\python.exe -m unittest -v mvp.tests.test_razer_worker_transport
```

Resultado: `18/18 PASS`.

Há ainda cinco testes de composição/launcher: default local, remoto
mockado sem rede, configuração por nomes de env customizados, fail-safe de
scope secret, default CPU validado do worker e confirmação de que o DIAO
permanece no Pi.

Regressão completa executada no estado final: `mvp/tests` = `77/77 PASS`;
`operational_guidance/diao/tests` = `10/10 PASS`; Core Raspberry =
`6/6 PASS`; UART Raspberry = `5/5 PASS`.

Cobertura de contrato comprovada com servidores HTTP reais em loopback e
providers fake. Estes testes não promovem ASR ou diarização acústica a PASS:

| Gate | Resultado |
|---|---:|
| ASR + turnos + embeddings + raciocínio pelos contratos existentes | PASS |
| compartilhamento da resposta entre três proxies | PASS |
| replay idempotente sem nova inferência | PASS |
| capacidade idempotente respeitada com oldest pending | PASS |
| `request_id` inclui endpoint/operação/payload | PASS |
| cache LRU de segmentos limitado | PASS |
| operação no endpoint errado recusada antes da inferência | PASS |
| bearer token e bind non-loopback fail-closed | PASS |
| HTTP non-loopback exige opt-in; HTTPS é o default | PASS |
| redirect 302 recusado sem encaminhar bearer token | PASS |
| hash adulterado recusado antes do provider | PASS |
| DIAO/PDF/ocorrência/histórico recusados no payload | PASS |
| limite de áudio | PASS |
| provider indisponível → `PROCESSING_PENDING` | PASS |
| ASR persistido antes de falha posterior de diarização | PASS |
| WAV preservado em falha | PASS |
| timeout retém spool e não remove owner vivo | PASS |
| TTL remove apenas spool expirado de processo morto | PASS |
| `KnowledgeProvider` mantido local | PASS |
| resposta forjada/truncada recusada | PASS |
| worker inacessível → `ProviderUnavailable` | PASS |

## Próximo gate de implantação

Provisionar token efêmero fora do Git, permitir no firewall somente Pi→Razer,
iniciar o worker com modelos locais auditados e executar um segmento controlado.
Até esse gate físico, o estado correto é `TRANSPORT READY / DEPLOYMENT PENDING`.
