# Motor de Reposición de Inventario

**Laboratorio 1 — Reproducibilidad y Orquestación de un Producto de ML**  
Maestría en Data Science | Product Development  
Universidad Galileo | Octubre 2026

## 1. Descripción del proyecto

Este proyecto implementa un sistema automatizado de pronóstico de demanda y recomendación de reposición de inventario para una cadena de supermercados, utilizando los datos públicos de Corporación Favorita.

El sistema genera pronósticos diarios por tienda y familia de productos para un horizonte de siete días. Además de estimar la demanda esperada, incorpora cuantiles de predicción para representar la incertidumbre y utiliza costos de negocio configurables para determinar las cantidades sugeridas de pedido.

La solución integra modelos de Machine Learning, control de versiones con Git, versionado de datos y modelos mediante DVC y orquestación de procesos con Apache Airflow 3.

El objetivo principal es garantizar que los pronósticos puedan generarse de forma automatizada y reproducirse posteriormente, utilizando las versiones correspondientes de código, datos, parámetros y modelos.

## 2. Fuente de datos

Se utiliza el conjunto de datos público **Store Sales – Time Series Forecasting**, correspondiente a Corporación Favorita, disponible en Kaggle:

https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data

Los archivos utilizados son:

- `train.csv`: ventas históricas diarias por tienda y familia de productos.
- `stores.csv`: información de tiendas, ciudades y agrupaciones.
- `holidays_events.csv`: información de feriados y eventos.
- `oil.csv`: precios históricos del petróleo.
- `transactions.csv`: transacciones por tienda y fecha.

Los archivos `test.csv` y `sample_submission.csv` no forman parte del laboratorio.

Las fuentes se conservan separadas del código y se utilizan para construir la carga histórica y la bandeja simulada de llegadas.

## 3. Arquitectura del sistema

El proyecto está organizado en módulos independientes que permiten separar la lógica de procesamiento de datos, el entrenamiento de modelos y la orquestación.

```text
motor_reposicion_inventario/
├── .github/workflows/
│   └── ci.yml
├── config/
│   └── params.yaml
├── dags/
│   └── inventory_dag.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── published/
│   └── snapshots/
├── evidencia/
├── models/
├── scripts/
│   ├── bootstrap_data.py
│   └── create_inbox.py
├── src/inventory/
│   ├── cli.py
│   ├── core.py
│   └── ingestion.py
├── tests/
│   └── test_inventory.py
├── Dockerfile
├── docker-compose.yaml
├── requirements.txt
├── README.md
├── DECISIONES.md
└── AGENTS.md
```

La lógica del producto se implementa en módulos de Python. Los DAGs de Airflow se encargan de coordinar las operaciones y sus dependencias.

## 4. Instalación y configuración

### Requisitos

- Python 3.11
- Git
- Docker Desktop y Docker Compose
- DVC 3 o superior
- Dependencias declaradas en `requirements.txt`

### Instalación de dependencias

En Windows PowerShell:

```powershell
py -m pip install -r requirements.txt
py -m pip install "dvc>=3"
```

### Preparación del conjunto de datos

Descargar el archivo ZIP de la competencia de Kaggle y ubicarlo en la carpeta principal del proyecto.

Ejecutar:

```powershell
py scripts/bootstrap_data.py datos_kaggle_original.zip
```

Este procedimiento prepara los archivos originales en `data/raw/`.

### Ejecución de pruebas

```powershell
$env:PYTHONPATH="src"
py -m pytest -q
```

### Entrenamiento y publicación

```powershell
py -m inventory.cli train --asof 2017-08-15
py -m inventory.cli publish --asof 2017-08-15
```

La primera instrucción entrena y compara los modelos. La segunda genera los pronósticos diarios y las cantidades sugeridas de pedido.

## 5. Modelado y evaluación

Se implementaron dos alternativas para estimar la demanda:

**Modelo baseline:** utiliza una combinación de ventas históricas rezagadas y promedios móviles como referencia inicial.

**Modelo de Machine Learning:** utiliza `HistGradientBoostingRegressor`, con funciones de pérdida cuantílica para generar los cuantiles P10, P50 y P90.

Ambos modelos se evalúan mediante el mismo esquema de validación temporal, evitando utilizar información posterior a la fecha de corte.

### Resultados de la evaluación

Se obtuvieron los siguientes resultados durante el entrenamiento correspondiente al corte del 15 de agosto de 2017:

| Métrica | Baseline | Machine Learning |
|---|---:|---:|
| MAE | 117.31 | 82.30 |
| Costo de negocio | 290.68 | 186.62 |
| Pinball loss P50 | 58.66 | 41.15 |
| Observaciones evaluadas | 49,896 | 49,896 |

El modelo de Machine Learning obtuvo una reducción aproximada del 29.8 % en MAE y del 35.8 % en costo de negocio respecto al baseline.

El criterio de selección implementado requiere que el modelo de Machine Learning mejore tanto el MAE como el costo de negocio del baseline. Bajo este criterio, el modelo seleccionado fue `ml`.

## 6. Generación de pronósticos y pedidos

El sistema produce un pronóstico diario por tienda y familia de productos, para un horizonte de siete días.

La ejecución correspondiente al 15 de agosto de 2017 generó **12,474 pronósticos**, equivalentes a 54 tiendas, 33 familias de productos y siete fechas de predicción.

Los archivos publicados contienen:

- Fecha de corte y fecha objetivo.
- Identificación de tienda y familia.
- Cuantiles P10, P50 y P90.
- Cantidad sugerida de pedido.
- Fracción crítica de negocio.
- Modelo utilizado.

La cantidad sugerida se calcula considerando el costo de faltante y el costo de excedente, definidos en `config/params.yaml`.

La fracción crítica utilizada es:

\[
q=\frac{C_u}{C_u+C_o}
\]

donde \(C_u\) representa el costo de faltante y \(C_o\) el costo de excedente.

Esto permite modificar las recomendaciones de pedido mediante parámetros de configuración, sin alterar el código del modelo.

## 7. Simulación del sistema de origen

Para representar las condiciones operativas de una empresa, se implementó una bandeja de archivos que simula la llegada periódica de información.

La bandeja se genera mediante:

```powershell
py scripts/create_inbox.py --days 35
```

El sistema contempla archivos de distintas fuentes, frecuencias de llegada y correcciones posteriores.

Durante las pruebas se generó una bandeja con **82 archivos**.

Esta carpeta se considera un sistema externo: los procesos de ingesta pueden consultar su contenido, pero no deben modificar los archivos originales.

La simulación permite evaluar el procesamiento por fecha de corte y el comportamiento ante información que llega posteriormente.

## 8. Orquestación con Apache Airflow 3

La ejecución automatizada se realiza mediante Apache Airflow 3, utilizando Docker Compose.

Para iniciar los servicios:

```powershell
docker compose up --build -d
```

La interfaz está disponible en:

http://localhost:8080

El DAG principal se denomina:

`inventory_daily`

El flujo contiene las siguientes tareas:

1. `ingest_validate`: ingesta y validación de las fuentes.
2. `prepare`: preparación de los datos.
3. `train_and_publish`: entrenamiento, selección del modelo y publicación de pronósticos.
4. `monitor_previous`: seguimiento del desempeño de pronósticos publicados.

La fecha lógica identifica el período procesado, independientemente del momento real de ejecución.

### Evidencia de ejecución

Se realizó una ejecución histórica correspondiente al 15 de agosto de 2017 mediante la interfaz de Apache Airflow.

Las cuatro tareas finalizaron con estado `success`, con una duración aproximada de 1 minuto y 40 segundos.

La evidencia de esta ejecución se encuentra en:

`evidencia/airflow_ejecucion_exitosa.png`

## 9. Versionado con Git y DVC

El proyecto utiliza Git para registrar las versiones del código, parámetros, configuraciones, DAGs y documentación.

Los datos y modelos se gestionan mediante DVC, evitando incorporarlos directamente al historial de Git.

Se versionaron las siguientes carpetas:

| Archivo DVC | Contenido |
|---|---|
| `data/raw.dvc` | Datos originales |
| `data/processed.dvc` | Datos procesados |
| `data/published.dvc` | Pronósticos publicados |
| `models.dvc` | Modelos entrenados |

El almacenamiento DVC utilizado durante las pruebas fue un remoto local, ubicado en `../dvc-storage`.

La configuración del remoto puede verificarse mediante:

```powershell
py -m dvc remote list
```

Las operaciones de almacenamiento y recuperación se realizan con:

```powershell
py -m dvc push
py -m dvc pull
```

Para reconstruir el proyecto en otro equipo sin acceso al remoto local, se utilizan los archivos originales de Kaggle y las instrucciones de preparación, entrenamiento y publicación descritas anteriormente.

## 10. Evidencia de reproducibilidad

Se realizó una prueba de recuperación y regeneración del pronóstico correspondiente al **15 de agosto de 2017**.

El objetivo fue comprobar que un resultado previamente publicado podía recuperarse mediante DVC y reproducirse con el mismo modelo y los mismos datos.

### Versión de código

El proyecto se registró inicialmente en Git mediante el commit:

```text
9380581
```

### Recuperación del pronóstico

Se utilizó el siguiente comando:

```powershell
py -m dvc checkout data/published.dvc --force
```

La recuperación restauró el archivo original de pronósticos.

Su huella SHA256 fue:

```text
B166EBD0411630D4FDEB26B23235EE0F086041753541BA19F2034C6295B6447E
```

### Regeneración

Posteriormente se volvió a ejecutar:

```powershell
$env:PYTHONPATH="src"
py -m inventory.cli publish --asof 2017-08-15
```

Se generaron nuevamente 12,474 pronósticos.

En la primera comparación se observó una diferencia entre los hashes de Windows y Linux, ocasionada por los saltos de línea utilizados al escribir el CSV.

La función `atomic_csv()` se ajustó para utilizar explícitamente `lineterminator="\n"`, garantizando un formato consistente entre sistemas operativos.

### Verificación final

Se calculó nuevamente la huella SHA256:

```powershell
(Get-FileHash "data/published/cutoff=2017-08-15/forecast.csv" -Algorithm SHA256).Hash
```

El resultado fue:

```text
B166EBD0411630D4FDEB26B23235EE0F086041753541BA19F2034C6295B6447E
```

**Los hashes del archivo original y del archivo regenerado coincidieron exactamente.**

De esta manera, se verificó tanto la recuperación de la versión publicada mediante DVC como la regeneración de un resultado idéntico byte por byte.

## 11. Integración continua con GitHub Actions

El repositorio incorpora un flujo de integración continua definido en `.github/workflows/ci.yml`.

Este workflow ejecuta las pruebas automatizadas de Python mediante `pytest`.

Se verificó una ejecución exitosa del workflow `tests`, con el trabajo `pytest` completado correctamente.

El desarrollo utiliza ramas independientes y Pull Requests. La rama principal `main` cuenta con una regla de protección configurada mediante GitHub Rulesets y controles de integración asociados a las pruebas automatizadas.

## 12. Seguimiento del desempeño

El producto incorpora una función de monitoreo que compara pronósticos publicados con ventas reales disponibles posteriormente.

El seguimiento permite calcular el error absoluto medio y la proporción de observaciones reales comprendidas entre los cuantiles P10 y P90.

Los reportes se almacenan en el directorio `reports/` y permiten analizar el comportamiento del producto conforme se incorporan nuevos datos.

## 13. Decisiones técnicas

Las decisiones sobre arquitectura, disponibilidad temporal de información, validación, selección de modelos, costos de negocio y manejo de correcciones se documentan en:

`DECISIONES.md`

El diseño prioriza la reproducibilidad, separación de responsabilidades y ejecución automatizada.

La solución trabaja con las ventas y características disponibles en el dataset. Para una operación real de inventario sería necesario incorporar existencias actuales, tiempos de abastecimiento, cantidades mínimas de pedido y restricciones logísticas adicionales.

## 14. Repositorio del proyecto

**GitHub:**  
https://github.com/sofiaesc07/motor-reposicion-inventario

El repositorio contiene el código fuente, configuraciones, DAGs, pruebas automatizadas, archivos de seguimiento DVC, documentación y evidencias de funcionamiento.

## 15. Almacenamiento de datos y modelos (DVC)

Los archivos versionados con DVC están almacenados en Google Drive:

[Acceder al almacenamiento DVC](https://drive.google.com/drive/folders/1A12QVBprY43fhtTgZKnqCUOaOWzyaACt)

El repositorio incluye la configuración del remoto en `.dvc/config`. Los archivos originales también pueden obtenerse desde Kaggle siguiendo las instrucciones de reproducción de este README.