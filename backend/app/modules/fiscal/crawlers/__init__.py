"""Auto-alimentação das matrizes fiscais a partir de fontes oficiais GRATUITAS
(CONFAZ, Dados Abertos SEFAZ) — reduz o cadastro manual e o custo de APIs pagas.

Arquitetura:
* `base.Extractor`  — contrato fetch()→parse()→extract(); I/O isolado do parsing.
* `confaz_cest`     — extrator concreto da relação NCM×CEST (Convênio 142/2018).
* `upsert`          — grava o resultado nas matrizes (idempotente, vigência-aware).
* `workers`         — tasks Celery (agendadas no beat) que orquestram tudo.
"""
