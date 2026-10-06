from fastapi import APIRouter, HTTPException, Depends
import asyncpg
import re
import unicodedata
from app.schemas import AlertaRapidoCreate, OcorrenciaTextoCreate
from app.nlp import extrair_dados_ocorrencia
from app.database import get_connection
from app.seguranca import exigir_api_key

router = APIRouter(prefix="/api/v1/ocorrencias", tags=["Ocorrências"])

def normalizar_texto(texto: str) -> str:
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', sem_acento).lower().strip()

@router.post("/alerta-rapido", dependencies=[Depends(exigir_api_key)])
async def registrar_alerta_rapido(dados: AlertaRapidoCreate, conn: asyncpg.Connection = Depends(get_connection)):
    status_map = {
        "VERDE": "TRANSITAVEL",
        "AMARELO": "TRANSITAVEL_ALERTA",
        "LARANJA": "INTRANSITAVEL_LEVES",
        "VERMELHO": "INTRANSITAVEL"
    }
    novo_status = status_map[dados.nivel]
    relato = f"[{dados.corporacao}] Alerta tatico: {dados.nivel}. {dados.observacao or ''}".strip()

    query = """
    WITH ponto_origem AS (
        SELECT ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), ST_SRID(geom)) AS ponto_geom
        FROM trechos_osm
        LIMIT 1
    ),
    via_proxima AS (
        SELECT t.id_trecho, t.name
        FROM trechos_osm t, ponto_origem p
        WHERE ST_DWithin(t.geom, p.ponto_geom, 150)
        ORDER BY t.geom <-> p.ponto_geom
        LIMIT 1
    )
    INSERT INTO estado_operacional_trechos (id_trecho, status, severidade, relato_origem, registrado_em)
    SELECT id_trecho, $3, $4, $5, NOW()
    FROM via_proxima
    ON CONFLICT (id_trecho) DO UPDATE
    SET status = EXCLUDED.status,
        severidade = EXCLUDED.severidade,
        relato_origem = EXCLUDED.relato_origem,
        registrado_em = NOW()
    RETURNING id_trecho, (SELECT name FROM via_proxima);
    """

    row = await conn.fetchrow(
        query,
        dados.longitude,
        dados.latitude,
        novo_status,
        dados.nivel,
        relato
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma via identificada num raio de 150 metros da coordenada informada."
        )

    return {
        "sucesso": True,
        "id_trecho": row["id_trecho"],
        "via": row["name"] or "Sem denominacao",
        "novo_status": novo_status,
        "severidade": dados.nivel
    }

@router.get("/ativas")
async def listar_ocorrencias_ativas(conn: asyncpg.Connection = Depends(get_connection)):
    query = """
    SELECT 
        e.id_estado,
        e.id_trecho,
        t.name AS nome_via,
        e.status,
        e.severidade,
        e.relato_origem,
        TO_CHAR(e.registrado_em, 'DD/MM HH24:MI') AS registrado_em
    FROM estado_operacional_trechos e
    JOIN trechos_osm t ON t.id_trecho = e.id_trecho
    WHERE e.status != 'TRANSITAVEL'
    ORDER BY e.registrado_em DESC
    LIMIT 50;
    """
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]

@router.post("/resetar-todas", dependencies=[Depends(exigir_api_key)])
async def resetar_todas_ocorrencias(conn: asyncpg.Connection = Depends(get_connection)):
    query = """
    UPDATE estado_operacional_trechos
    SET status = 'TRANSITAVEL',
        severidade = 'BAIXA',
        relato_origem = 'Operacao encerrada. Vias normalizadas.',
        registrado_em = NOW()
    WHERE status != 'TRANSITAVEL'
    RETURNING id_trecho;
    """
    rows = await conn.fetch(query)
    return {"sucesso": True, "trechos_liberados": len(rows)}

@router.post("/processar-texto", dependencies=[Depends(exigir_api_key)])
async def processar_texto(dados: OcorrenciaTextoCreate, conn: asyncpg.Connection = Depends(get_connection)):
    extraido = extrair_dados_ocorrencia(dados.texto)

    if not extraido["via"]:
        raise HTTPException(
            status_code=422,
            detail="Nao consegui identificar a via no texto. Informe o nome da rua ou use o alerta rapido com coordenadas."
        )
    if not extraido["status"]:
        raise HTTPException(
            status_code=422,
            detail="Nao consegui identificar a situacao da via (alagada, bloqueada, liberada...)."
        )

    termo_limpo = normalizar_texto(extraido["via"])
    ignorar = ("avenida", "rua", "alameda", "estrada", "rodovia", "av", "r")
    palavras = [w for w in termo_limpo.split() if w not in ignorar]
    termo_busca = " ".join(palavras) if palavras else termo_limpo

    if len(termo_busca) < 3:
        raise HTTPException(status_code=422, detail="Nome da via curto demais para buscar com seguranca.")

    query = """
    WITH vias_candidatas AS (
        SELECT 
            id_trecho,
            name,
            GREATEST(
                similarity(translate(lower(name), 'áàâãéêíóôõúç', 'aaaaeeiooouc'), $4),
                word_similarity($4, translate(lower(name), 'áàâãéêíóôõúç', 'aaaaeeiooouc'))
            ) AS score_sim
        FROM trechos_osm
        WHERE name IS NOT NULL
          AND (
              translate(lower(name), 'áàâãéêíóôõúç', 'aaaaeeiooouc') % $4
              OR word_similarity($4, translate(lower(name), 'áàâãéêíóôõúç', 'aaaaeeiooouc')) >= 0.35
          )
        ORDER BY score_sim DESC
        LIMIT 50
    )
    INSERT INTO estado_operacional_trechos (id_trecho, status, severidade, relato_origem, registrado_em)
    SELECT id_trecho, $1, $2, $3, NOW()
    FROM vias_candidatas
    ON CONFLICT (id_trecho) DO UPDATE
    SET status = EXCLUDED.status,
        severidade = EXCLUDED.severidade,
        relato_origem = EXCLUDED.relato_origem,
        registrado_em = NOW()
    RETURNING id_trecho, (SELECT name FROM vias_candidatas vc WHERE vc.id_trecho = estado_operacional_trechos.id_trecho);
    """

    rows = await conn.fetch(query, extraido["status"], extraido["severidade"], dados.texto, termo_busca)

    if not rows:
        raise HTTPException(status_code=404, detail=f"Nenhuma via encontrada para '{extraido['via']}'.")

    nomes_afetados = list({r["name"] for r in rows if r["name"]})

    return {
        "sucesso": True,
        "trechos_atualizados": len(rows),
        "termo_buscado": extraido["via"],
        "termo_normalizado": termo_busca,
        "vias_identificadas": nomes_afetados,
        "status_definido": extraido["status"],
        "severidade": extraido["severidade"]
    }

