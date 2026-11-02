# Motor de Reposición de Inventario — Laboratorio 1

Maestría en Data Science, Product Development, octubre 2026.

## Qué produce
- Pronóstico por **día, tienda y familia** para los próximos siete días, con cuantiles P10/P50/P90.
- Sugerencia de pedido a partir del cuantil de negocio y de costos configurados.
- Comparación temporal baseline vs. ML (MAE, pérdida cuantílica y costo de negocio), y seguimiento de predicciones publicadas.
- Orquestación con Airflow 3, pruebas en CI y diseño para Git + DVC.

## Requisitos
Python 3.11, Docker Desktop + Docker Compose, Git, DVC >= 3, cuenta GitHub y un remoto DVC.

## Instalación local desde cero
```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap_data.py /ruta/store-sales-time-series-forecasting.zip
# Windows: set PYTHONPATH=src; macOS/Linux: export PYTHONPATH=src
python -m pytest -q
python -m inventory.cli validate
python -m inventory.cli train --asof 2017-08-15
python -m inventory.cli publish --asof 2017-08-15
python -m inventory.cli monitor --publication data/published/cutoff=2017-08-15/forecast.csv
```
`2017-08-15` es la última fecha del training público. Para monitoreo retrospectivo, generar primero una publicación en una fecha anterior y usar las ventas posteriores para contrastar resultados.

## Simular sistema de origen sin tocar el original
```bash
python scripts/create_inbox.py --days 35
```
Esto crea `source_inbox/sales_YYYY-MM-DD.csv`, además de archivos fechados de petróleo, transacciones y feriados con distintas frecuencias y un ejemplo de revisión de ventas con fecha de llegada explícita. La bandeja se trata como externa y nunca se modifica desde Airflow. La fecha del archivo de las otras fuentes indica llegada, aunque sus registros pueden abarcar distintos días.

## Airflow 3 con Docker
```bash
docker compose up --build -d
# Interfaz http://localhost:8080
# Usuario admin; consultar la contraseña generada por el gestor de autenticación en los logs del servidor
# Dag: inventory_daily
```
**Importante:** verificar compatibilidad exacta de Airflow 3 y credenciales antes de evaluación; no se ha probado Docker en el entorno de generación. La fecha lógica del DAG es el corte del pronóstico. Para backfill consultar `airflow backfill create --help` y ejecutar sobre fechas históricas con origen preparado.

## DVC: configurar remoto real
```bash
dvc init
dvc add data/raw
dvc add data/processed  # solo si contiene resultados
dvc add models          # solo si contiene resultados
dvc add data/published  # solo si contiene resultados
# Ejemplo de almacenamiento compartido, configurar con URL REAL:
# dvc remote add -d storage s3://TU-BUCKET/inventory
# dvc remote modify storage region TU-REGION
# dvc push
# git add .dvc .gitignore data/*.dvc models.dvc config src dags tests README.md DECISIONES.md
# git commit -m "chore(data): track raw processed models forecasts with dvc"
# git push
```
Cuando los artefactos cambian, volver a hacer `dvc add`, `dvc push` y commit de los punteros `.dvc`. Para entregas automáticas es necesario agregar una política explícita y credenciales seguras para publicar los artefactos DVC; no deben guardarse secretos en Git.

## Flujo de GitHub
Crear un repo; trabajar con ramas `feat/`, `fix/`, `docs/`; PR obligatorio, aprobación y checks `pytest` exitosos. Configurar Rulesets para proteger `main`. Crear al entregar: `git tag entrega-lab1 && git push origin entrega-lab1`.

## Evidencias pendientes en una computadora operativa
- Capturas de ejecución real de DAG en Airflow y logs sin errores.
- Comparación de métricas baseline/ML tras entrenamiento real.
- Archivos DVC y comprobación `git clone` + `dvc pull` desde un equipo distinto.
- Validación del caso de pruebas ocultas y de formato de bandeja GES cuando sea conocido.

## Decisiones y restricciones
Ver `DECISIONES.md`. El modelo no utiliza valores de fuentes futuras con fecha de publicación desconocida. Un producto real requiere stock actual, lead time, tamaño de empaque y reglas de perecederos para convertir demanda en orden neta real.

## Cambios del enunciado individual (noviembre 2026)
- Cada estudiante crea su propia carga histórica y bandeja a partir de los cinco CSV de Kaggle. No se espera un ZIP adicional del docente.
- La evaluación reconstruirá el producto ubicando los archivos de Kaggle en la ruta documentada y verificará el flujo en fechas no publicadas.
- Los datos y modelos se versionan con DVC; no se incluyen en el historial Git.
- Se requiere en este README evidencia verificable de reproducir un pronóstico anterior. **Pendiente de completar con comandos, commit, hashes y resultados reales en la computadora del estudiante**. No se inventan resultados de Airflow o DVC.

### Guion de evidencia de reproducción (completar al ejecutar)
```bash
# Después de publicar una fecha y confirmar/push los punteros .dvc:
git rev-parse HEAD
git status --short
dvc status
sha256sum data/published/cutoff=FECHA/forecast.csv
# En un clon limpio, mismo commit y remoto DVC configurado:
git checkout COMMIT_REGISTRADO
dvc pull
sha256sum data/published/cutoff=FECHA/forecast.csv
```
Registrar aquí el commit y ambos hashes, que deben coincidir. En Windows PowerShell puede usarse `Get-FileHash -Algorithm SHA256 RUTA` en lugar de `sha256sum`.
