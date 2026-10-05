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