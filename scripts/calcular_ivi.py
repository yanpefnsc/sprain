import os
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("Calculando o Indice de Vulnerabilidade de Intransitabilidade (IVI)...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS ivi_score double precision;"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS classe_risco text;"))

        # Calculo ponderado:
        # 1. Proximidade fluvial (peso 35%)
        # 2. Relevo plano / depressao (peso 25%)
        # 3. Cota altimetrica relativa (peso 15%)
        # 4. Suscetibilidade física (peso 15%)
        # 5. Ocorrencias historicas CGE (peso 10%)
        conn.execute(text("""
            WITH normalizado AS (
                SELECT 
                    id_trecho,
                    GREATEST(0, (1 - LEAST(distancia_agua_m, 1000) / 1000.0)) * 35 AS f_agua,
                    (CASE WHEN classe_declividade = 1.0 THEN 1.0 WHEN classe_declividade = 2.0 THEN 0.5 ELSE 0.1 END) * 25 AS f_decliv,
                    ((820.0 - LEAST(GREATEST(altitude_media, 736.0), 820.0)) / (820.0 - 736.0)) * 15 AS f_alt,
                    (CASE 
                        WHEN grau_suscetibilidade = 'Muito Alto' THEN 1.0
                        WHEN grau_suscetibilidade = 'Alto' THEN 0.75
                        WHEN grau_suscetibilidade = 'Medio' THEN 0.4
                        ELSE 0.1
                    END) * 15 AS f_susc,
                    LEAST(total_alagamentos, 5) / 5.0 * 10 AS f_cge
                FROM trechos_osm
            )
            UPDATE trechos_osm t
            SET 
                ivi_score = ROUND((n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge)::numeric, 2),
                classe_risco = CASE 
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 70 THEN 'Critico'
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 50 THEN 'Alto'
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 30 THEN 'Medio'
                    ELSE 'Baixo'
                END
            FROM normalizado n
            WHERE t.id_trecho = n.id_trecho;
        """))

    print("Passo 7 concluido: IVI calculado para todos os trechos!")

if __name__ == "__main__":
    main()
