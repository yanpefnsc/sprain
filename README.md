# SPRAIN • Plataforma de Gestão Tática de Intransitabilidade Viária

Sistema geoespacial integrado para mitigação de risco de enchentes, roteamento de emergência e apoio à decisão operacional no distrito de Itaquera (São Paulo/SP).

---

## 🚀 Funcionalidades Principais

- **Modelagem IVI:** Cálculo do Índice de Vulnerabilidade de Intransitabilidade via relevo, proximidade hidrográfica e histórico CGE.
- **Sala de Situação Central (`/`):**
  - Mapa vetorial com estilos de alto contraste.
  - Sincronização em tempo real de vias bloqueadas.
  - Cálculo de **Rota Segura** contornando vias com retenção hídrica.
  - Simulador de cenários pluviométricos (mm).
  - Exportação de Boletins Oficiais em CSV e JSON.
- **Terminal de Campo para Viaturas (`/static/campo.html`):**
  - Georreferenciamento e resolução reversa de logradouro em tempo real via PostGIS.
  - Despacho tático por toque de severidade (Transitável, Atenção, Crítico Leve, Intransitável).
  - Atalhos de viatura para simulação e homologação de rotas.

---

## 🛠️ Stack Tecnológica

- **Banco de Dados Espacial:** PostgreSQL 16 + PostGIS 3.4
- **Backend:** FastAPI (Python) com `asyncpg`
- **Frontend / GIS Web:** MapLibre GL JS, OpenStreetMap e CartoDB Dark Matter
- **Infraestrutura:** Docker e Docker Compose

---

## 📦 Como Subir com Docker

```bash
docker compose up --build -d
## 🚀 Arquitetura Regional & Validação Científica (v1.2.0)

### 📊 Comprovação Empírica do IVI (Índice de Vulnerabilidade a Alagamentos)
Cruzamento espacial de eventos históricos registrados pela CGE contra a malha viária indexada:

| Escopo Analisado | Amostra | IVI Médio | % Risco Alto / Crítico |
| :--- | :--- | :--- | :--- |
| **Malha Viária Geral** | 2.978 trechos | 48.7 | 46.3% |
| **Trechos com Histórico de Alagamento** | Vias validadas | **63.0** | **66.7%** |

### 🛣️ Roteamento Hierárquico em Dois Níveis (Macro & Micro)
Para viabilizar escala estadual sem degradação de memória em consultas `pgRouting`:
* **Camada Macro (Corredor Estruturante):** 245.0 km contínuos ligando Araraquara a São Paulo via SP-310 (Washington Luís), SP-330 (Anhanguera) e SP-348 (Bandeirantes).
* **Camada Micro (Polígonos Urbanos Dinâmicos):** Extração sob demanda de eixos municipais (857 eixos estruturantes em Araraquara e malha metropolitana em São Paulo).
* **Endpoint B2B:** `GET /api/v1/rotas/intermunicipal?origem=Araraquara&destino=Sao%20Paulo`
