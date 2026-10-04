"""Gera trechos_itaquera: só os trechos de rua que tocam o distrito de Itaquera.

Precisa das tabelas distritos_bruto e trechos_bruto já carregadas.
"""
import os

from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")
motor = create_engine(URL_BANCO)

with motor.begin() as conn:
    colunas_texto = conn.execute(text("""
        select column_name from information_schema.columns
        where table_name = 'distritos_bruto'
          and data_type in ('text', 'character varying')
    """)).scalars().all()

    coluna_nome = None
    for col in colunas_texto:
        achou = conn.execute(
            text(f'select count(*) from distritos_bruto where upper("{col}") = \'ITAQUERA\'')
        ).scalar()
        if achou:
            coluna_nome = col
            break

    if coluna_nome is None:
        raise SystemExit(f"Nenhuma coluna de distritos_bruto tem o valor ITAQUERA. Colunas de texto: {colunas_texto}")

    print(f"nome do distrito está na coluna '{coluna_nome}'")

    conn.execute(text("drop table if exists distrito_itaquera"))
    conn.execute(text(f"""
        create table distrito_itaquera as
        select * from distritos_bruto where upper("{coluna_nome}") = 'ITAQUERA'
    """))

    conn.execute(text("drop table if exists trechos_itaquera"))
    conn.execute(text("""
        create table trechos_itaquera as
        select row_number() over () as id_trecho, t.*
        from trechos_bruto t
        join distrito_itaquera d on st_intersects(t.geom, d.geom)
    """))
    conn.execute(text("alter table trechos_itaquera add primary key (id_trecho)"))
    conn.execute(text("create index on trechos_itaquera using gist (geom)"))

    total = conn.execute(text("select count(*) from trechos_itaquera")).scalar()
    print(f"{total} trechos em Itaquera")
