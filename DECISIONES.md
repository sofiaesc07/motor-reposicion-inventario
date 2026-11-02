# Decisiones técnicas y de producto

1. **Horizonte:** 7 días por tienda y familia, una fila por fecha objetivo.
2. **Datos disponibles en el corte:** únicamente ventas fechadas hasta el corte; el dataset Kaggle no ofrece timestamps de publicación para petróleo, transacciones o feriados, por lo que esas fuentes se conservan y validan como entradas, pero no se utilizan como features futuras sin evidencia de disponibilidad.
3. **Baseline:** combinación de ventas de hace 6 y 13 días y promedio de las 4 semanas previas; las primeras dos fechas son comparables por día de semana solo parcialmente, por lo que este baseline es una aproximación simple. Se usa idéntica construcción de features para ambos modelos.
4. **ML:** Gradient Boosting cuantílico (P10/P50/P90), con horizonte explícito y variables causales. Se selecciona solo si supera a baseline tanto en MAE como en costo de negocio de validación temporal.
5. **Costos:** newsvendor: cu/(cu+co), interpolando los cuantiles disponibles. Con cu=5 y co=1, la probabilidad objetivo es 0.8333. Los pedidos son objetivos de demanda estimados, no pedidos netos reales sin inventario inicial, lead time, unidades/cajas, vida útil y compras pendientes.
6. **Fuente de datos:** datos públicos originales de Kaggle, con simulación local de `source_inbox`. La nueva consigna individual exige construir la bandeja a partir de los CSV originales. Se generan archivos separados por fuente y fecha de llegada, con frecuencias distintas y revisión tardía de ventas; se conserva la fuente sin alterar.
7. **Idempotencia:** salida particionada por fecha de corte, archivo atómico de reemplazo, validación de llaves y correcciones elegidas por revisión mayor. No modificar fuente externa.
8. **Modelo vigente:** entrenado una vez por corte en el DAG. Esto es conservador para fugas, aunque costoso. Para producción, considerar entrenamiento menos frecuente y una política de promoción.
9. **Versionado:** Git para código/configuración, DVC para datos, snapshots, modelos y pronósticos. Un `dvc pull` real requiere configurar un remoto compartido con permiso al docente; un remoto solo local no cumple el requisito de evaluación.
10. **Limitaciones:** precios y stock inicial no disponibles en Kaggle; costos son supuestos configurables. No se reportan métricas de modelos sin ejecutarlos ni se considera el ZIP original equivalente a la bandeja GES.

11. **Evaluación revisada:** el docente reconstruirá el proyecto desde los CSV originales. Los comandos y hashes reales de reproducción con DVC quedan pendientes de ejecutar y documentar en README.
12. **Límite temporal:** el histórico público carece de timestamps reales de disponibilidad. Los cortes de datos se filtran por fecha observada y la bandeja sintética modela fecha de llegada; no se debe presentar esta simulación como evidencia histórica de disponibilidad real.
