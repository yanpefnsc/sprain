import re
import asyncpg
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_connection
from app.nlp import extrair_logradouros_e_status

router = APIRouter(prefix="/api/v1/ocorrencias", tags=["Relatos e Ingestao Textual"])

class RelatoTextoInput(BaseModel):
    texto: str
    fonte: Optional[str] = "OPERACIONAL"

class DetalheTrechoAfetado(BaseModel):
    id_trecho: int
    nome_oficial: Optional[str] = None
    termo_extraido: str
    status_aplicado: str

class ResultadoIngestao(BaseModel):
    relato: str
    status_atribuido: str
    vias_detectadas: List[str]
    trechos_atualizados: int
    detalhes: List[DetalheTrechoAfetado]

def sanitizar_para_busca(nome_via: str) -> str:
    # Remove prefixos como 'Avenida ', 'Rua ', etc. para coincidir com a toponimia OSM
    limpo = re.sub(r"^(?:rua|r\.|av\.|avenida|travessa|tv\.|estrada|estr\.|alameda|al\.)\s+", "", nome_via, flags=re.IGNORECASE)
    return limpo.strip()

@router.post("/processar-texto", response_model=ResultadoIngestao)
async def processar_relato_textual(
    payload: RelatoTextoInput,
    conn: asyncpg.Connection = Depends(get_connection)
):
    resultado_nlp = extrair_logradouros_e_status(payload.texto)
    status = resultado_nlp["status"]
    vias = resultado_nlp["candidatos_vias"]
    
    trechos_afetados: List[DetalheTrechoAfetado] = []
    
    for via in vias:
        termo_busca = sanitizar_para_busca(via)
        
        query_busca = '''
            SELECT id_trecho, name, COALESCE(ivi_score, 0) as ivi_score
            FROM trechos_osm
            WHERE name ILIKE '%' || $1 || '%'
            ORDER BY ivi_score DESC
            LIMIT 10;
        '''
        candidatos = await conn.fetch(query_busca, termo_busca)
        
        for cand in candidatos:
            id_trecho = cand["id_trecho"]
            await conn.execute('''
                INSERT INTO estado_operacional_trechos (id_trecho, status, relato_origem, registrado_em)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (id_trecho) 
                DO UPDATE SET status = EXCLUDED.status, 
                              relato_origem = EXCLUDED.relato_origem, 
                              registrado_em = NOW();
            ''', id_trecho, status, payload.texto)
            
            trechos_afetados.append(DetalheTrechoAfetado(
                id_trecho=id_trecho,
                nome_oficial=cand["name"],
                termo_extraido=via,
                status_aplicado=status
            ))

    return ResultadoIngestao(
        relato=payload.texto,
        status_atribuido=status,
        vias_detectadas=vias,
        trechos_atualizados=len(trechos_afetados),
        detalhes=trechos_afetados
    )

@router.get("/ativas")
async def listar_interdicoes_ativas(conn: asyncpg.Connection = Depends(get_connection)):
    query = '''
        SELECT e.id_trecho, t.name, e.status, e.relato_origem, e.registrado_em
        FROM estado_operacional_trechos e
        JOIN trechos_osm t ON t.id_trecho = e.id_trecho
        ORDER BY e.registrado_em DESC;
    '''
    rows = await conn.fetch(query)
    return [dict(r) for r in rows]
