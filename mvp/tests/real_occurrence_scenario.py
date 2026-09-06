"""Harness-only fictional truth. Never import this module from inference code."""
from pathlib import Path
import json
from operational_guidance.diao.provider import DIAOKnowledgeProvider

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'mvp/evidence/real_occurrence_01'


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    provider = DIAOKnowledgeProvider()
    query = 'atrito verbal desentendimento ameaça ofensa sem lesão'
    hits = provider.search(query, top_k=5)
    section = provider.get_section('B01.147')
    assert section and section['source_sha256'] == '747B1EE9E50FC799053CD34F00DCE848DF8EB75AB99B73FE9E92967B1CC91ADA'
    (OUT / 'diao_pre_scenario_lookup.json').write_text(json.dumps({'query':query,'hits':hits,'selected':section}, ensure_ascii=False, indent=2), encoding='utf-8')
    people = {
        'OFFICER_01': {'voice':'Microsoft Daniel','role':'KNOWN_OFFICER','name':'Renato Lumeral'},
        'OFFICER_02': {'voice':'Microsoft Mark','role':'KNOWN_OFFICER','name':'Caio Verdanil'},
        'CIVIL_01': {'voice':'Microsoft Maria','role':'POSSIBLE_VICTIM','name':'Lia Terenal'},
        'CIVIL_02': {'voice':'Microsoft David','role':'POSSIBLE_INVOLVED','name':'Bruno Solvar'},
        'CIVIL_03': {'voice':'Microsoft Zira','role':'POSSIBLE_WITNESS','name':'Nara Velum'},
    }
    # Ordinary Portuguese, unmodified pitch, no script text passed to ASR.
    turns = [
      ('OFFICER_01', 'Boa tarde. Meu nome é Renato Lumeral. Sou policial militar. Estamos atendendo a solicitação de uma discussão entre vizinhos na Rua das Lanternas Azuis, número cento e vinte, no bairro Jardim do Horizonte Imaginário. Minha equipe vai ouvir cada pessoa separadamente. Pode explicar o que aconteceu?', 3),
      ('CIVIL_01', 'Meu nome é Lia Terenal. Eu chamei a polícia porque fiquei com medo. Bruno disse que iria me machucar quando eu saísse de casa. A discussão começou por causa de duas caixas deixadas na passagem. Não fui agredida fisicamente e não estou ferida. Quero relatar as palavras que ouvi.', 3),
      ('OFFICER_01', 'Estou registrando a sua declaração. Preciso distinguir o que a senhora viu do que ouviu de outra pessoa. Explique onde estava, qual foi a sequência da discussão e se alguém presenciou as palavras mencionadas. O horário que informar será registrado como sua estimativa.', 3),
      ('CIVIL_01', 'Eu estava no portão da residência. Ele chegou às oito horas e começou a reclamar das caixas. Pedi que conversasse sem gritar. Ele respondeu que iria me machucar. A vizinha Nara estava na janela. Eu não vi arma nem contato físico entre nós. Estou falando do que ouvi diretamente.', 3),
      ('OFFICER_02', 'Boa tarde. Meu nome é Caio Verdanil. Sou policial militar e trabalho com Renato. Vou ouvir sua versão aqui, um pouco afastado da outra parte. Não estamos decidindo quem está certo. Explique com suas palavras o motivo do desentendimento e aquilo de que se recorda.', 3),
      ('CIVIL_02', 'Meu nome é Bruno Solvar. A reclamação foi dirigida a mim. Eu reclamei porque havia caixas na passagem. Falei alto e me arrependo disso, mas nego ter dito que iria machucar Lia. Minha versão é que eu disse que procuraria resolver o problema da passagem. Não houve contato físico.', 3),
      ('OFFICER_02', 'Estou anotando essa diferença entre as declarações. Pode informar sua estimativa de horário e dizer se já existia algum desentendimento anterior? Se não lembrar de alguma palavra, prefiro que diga que não lembra. Vou registrar sua resposta sem completar o que não foi informado.', 3),
      ('CIVIL_02', 'Eu cheguei depois das dez horas. Não cheguei às oito. As caixas estavam junto ao portão, e eu precisava passar. Não tenho certeza de todas as palavras porque estava nervoso. Já tínhamos conversado sobre a passagem em outro dia. Naquele dia também não houve agressão física.', 3),
      ('OFFICER_01', 'Agora vamos ouvir a vizinha que estava na janela. Peço que cada pessoa aguarde em seu espaço enquanto concluímos as declarações. A coleta continua aberta. Não é necessário repetir a discussão. Vamos dar alguns instantes para todos se acalmarem antes de retomar o atendimento.', 90),
      ('OFFICER_02', 'Retomando o atendimento. Continuo aqui com meu colega e vou ouvir a pessoa que presenciou parte do episódio. A senhora pode se apresentar e dizer de onde observou os fatos? Gostaria que relatasse apenas aquilo que viu e ouviu diretamente, sem tentar escolher uma das versões.', 3),
      ('CIVIL_03', 'Meu nome é Nara Velum. Eu estava na janela da minha casa e vi os dois discutindo perto do portão. Havia duas caixas na passagem. Ouvi Bruno dizer que iria machucar Lia. Não vi empurrão, soco ou arma. Não sei dizer o que aconteceu antes de eu chegar à janela.', 3),
      ('OFFICER_02', 'A senhora consegue explicar por que se recorda dessas palavras e se tem alguma referência de horário? Também preciso registrar o que não conseguiu observar. Não se preocupe em preencher lacunas. Se não tiver certeza, essa incerteza será mantida no registro.', 3),
      ('CIVIL_03', 'Olhei para o relógio da cozinha pouco antes de ir à janela. Eram oito horas. A voz estava alta e por isso ouvi a frase. Não tenho gravação. Não sei se existiu conversa anterior entre eles. Vi as caixas, ouvi a discussão e não vi agressão física naquele intervalo.', 3),
      ('OFFICER_01', 'Caio, temos versões diferentes sobre o horário e sobre as palavras utilizadas. A vizinha confirma a presença das caixas e relata ter ouvido a frase. Vamos conservar essas diferenças nas declarações. A natureza que o sistema sugerir será uma hipótese provisória, sujeita à nossa avaliação.', 3),
      ('OFFICER_02', 'Renato, concordo em registrar separadamente cada relato. Não temos gravação e não fizemos confirmação documental dos nomes declarados. Minha entrevista com Bruno foi feita em separado. Vamos verificar as referências apresentadas pelo sistema e registrar apenas as providências efetivamente realizadas nesta simulação.', 3),
      ('CIVIL_01', 'Sou Lia novamente. Continuo com medo por causa da frase que ouvi. Quero acrescentar que as caixas eram minhas e seriam retiradas naquele dia. Não tenho mensagem escrita sobre a discussão. Não estou dizendo que vi uma arma. Minha declaração é sobre as palavras e o tom da conversa.', 3),
      ('CIVIL_02', 'Sou Bruno novamente. Mantenho a minha versão sobre a discussão e reconheço que falei alto. Não quero continuar o desentendimento. As caixas me incomodaram, mas não peguei nenhum objeto da Lia. Concordo em aguardar separado enquanto o atendimento é encerrado. Não houve nova discussão durante a espera.', 3),
      ('OFFICER_01', 'Estamos organizando as declarações e as referências recebidas. Os nomes permanecem autodeclarados. As versões incompatíveis continuarão identificadas como divergências. Nenhuma inferência do sistema será registrada como certeza sobre responsabilidade. Peço que avisem se ainda falta alguma informação que presenciaram diretamente.', 3),
      ('CIVIL_03', 'Eu vi somente aquela parte perto do portão. Depois que a equipe chegou, as pessoas ficaram separadas e não ouvi outra discussão. Não posso confirmar o que cada pessoa pretendia fazer. Meu relato termina no que pude observar da janela e durante o atendimento.', 3),
      ('OFFICER_02', 'Conferi que as três pessoas foram ouvidas nesta simulação. A apresentação de documentos continua pendente, portanto não há identidade documental confirmada. As declarações sobre ausência de ferimento foram registradas como relatos. Não foi acrescentado nenhum resultado de exame médico porque ele não ocorreu.', 3),
      ('CIVIL_01', 'Não tenho outro fato para acrescentar agora. Agradeço por terem registrado minha versão sem apagar a diferença em relação ao que Bruno informou. Meu nome foi apenas declarado durante a conversa. Eu não apresentei documento nesta simulação. Quero que minha declaração permaneça vinculada às palavras que falei.', 3),
      ('CIVIL_02', 'Também não tenho informação nova. Confirmo que fui ouvido separadamente e que minha versão foi registrada. Não apresentei documento nesta simulação. Não houve nova aproximação ou discussão depois da chegada da equipe. Continuo discordando da frase atribuída a mim, conforme já expliquei.', 3),
      ('OFFICER_01', 'Caio, vamos encerrar a coleta. O histórico deverá manter as declarações, as divergências, os nomes autodeclarados, as referências consultadas e as pendências. O documento gerado será um rascunho preliminar para revisão. O encerramento da gravação não transforma esse rascunho em registro oficial.', 3),
      ('OFFICER_02', 'Entendido, Renato. A coleta poderá ser finalizada pelo relógio. As providências marcadas ficarão registradas como ações desta simulação. O relatório deve informar suas limitações, incluindo qualquer dificuldade de transcrição ou de separação das vozes. Depois da finalização, vamos conferir o histórico e o rascunho produzido.', 4),
    ]
    utterances = [dict(id=f'utterance_{i:03d}',speaker=s,voice=people[s]['voice'],text=t,silence_after=p) for i,(s,t,p) in enumerate(turns,1)]
    # Semantic propositions are evaluator inputs only; never prompts or model context.
    expected = [
      (2,['chamei','policia']), (2,['medo']), (2,['machucar']),
      (2,['caixas','passagem']), (2,['nao','ferida']),
      (4,['portao']), (4,['oito']), (4,['nara','janela']), (4,['nao','arma']),
      (6,['bruno']), (6,['falei','alto']), (6,['nego','machucar']), (6,['nao','contato','fisico']),
      (8,['depois','dez']), (8,['nervoso']),
      (11,['janela']), (11,['caixas']), (11,['ouvi','machucar']), (11,['nao','arma']),
      (13,['oito']), (13,['nao','gravacao']),
      (16,['caixas','minhas']), (16,['nao','mensagem']),
      (17,['falei','alto']), (17,['nao','nova','discussao']),
      (19,['separadas']), (20,['documentos','pendente']),
      (21,['nao','documento']), (22,['nao','documento']),
    ]
    truth = dict(synthetic_only=True, source='entirely fictional harness scenario',
                 selected_diao_nature='B01.147 - AMEAÇA', diao_pages=[102,103], diao_section='B01.147',
                 diao_item=[h['item'] for h in section['chunks'] if h['page']['pdf']==103 and h['section']['subsection']=='PELA POLÍCIA MILITAR'],
                 participants=people, utterances=utterances, long_silence_seconds=90,
                 expected_facts=[{'id':f'E{i:03d}','utterance_id':f'utterance_{u:03d}','anchors':a} for i,(u,a) in enumerate(expected,1)],
                 pre_registered=dict(asr_wer_max=.25, speaker_count=5, false_merges=0,false_splits=0,der_max=.20,
                   role_accuracy_min=1.0,fact_recall_min=.85,hallucinations=0, max_diarization_iterations=3,
                   inference_iteration=2, noise_only_after_clean_pass=True))
    (OUT/'scenario_ground_truth.json').write_text(json.dumps(truth,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ground_truth':str(OUT/'scenario_ground_truth.json'),'turns':len(turns),'voices':5,'nature':truth['selected_diao_nature']}))

if __name__ == '__main__':
    prepare()
