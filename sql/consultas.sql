-- Consultas de ejemplo sobre el data warehouse (data/warehouse/dw_suicidios.db)
-- Ejecutar con:  sqlite3 data/warehouse/dw_suicidios.db < sql/consultas.sql

.headers on
.mode column

-- 1. Tasa por 100.000 habitantes (5 años y más) por región natural y sexo, 2015-2024
SELECT d.region,
       m.sexo,
       SUM(h.casos)                                        AS casos,
       ROUND(SUM(h.casos) * 100000.0 / SUM(h.poblacion), 2) AS tasa_100k
FROM hechos_suicidio h
JOIN dim_departamento d ON h.cod_dpto = d.cod_dpto
JOIN dim_demografia  m ON h.id_demografia = m.id_demografia
GROUP BY d.region, m.sexo
ORDER BY tasa_100k DESC;

-- 2. Tasa nacional por año, marcando el cambio de serie poblacional y el año provisional
SELECT t.anio,
       t.serie_poblacion,
       t.anio_provisional,
       SUM(h.casos)                                        AS casos,
       ROUND(SUM(h.casos) * 100000.0 / SUM(h.poblacion), 2) AS tasa_100k
FROM hechos_suicidio h
JOIN dim_tiempo t ON h.anio = t.anio
GROUP BY t.anio
ORDER BY t.anio;

-- 3. Tasa por ciclo de vida y sexo
SELECT m.ciclo_vida,
       m.sexo,
       ROUND(SUM(h.casos) * 100000.0 / SUM(h.poblacion), 2) AS tasa_100k
FROM hechos_suicidio h
JOIN dim_demografia m ON h.id_demografia = m.id_demografia
GROUP BY m.ciclo_vida, m.sexo
ORDER BY m.sexo, tasa_100k DESC;

-- 4. Diez departamentos con mayor tasa ajustada por edad y sexo
SELECT departamento, casos, tasa_cruda, tasa_ajustada, smr, puesto_casos, puesto_tasa_ajustada
FROM tasas_departamento
ORDER BY tasa_ajustada DESC
LIMIT 10;

-- 5. Validaciones de la carga
SELECT 'duplicados en la llave' AS validacion, COUNT(*) AS resultado
FROM (SELECT cod_dpto, anio, id_demografia FROM hechos_suicidio
      GROUP BY cod_dpto, anio, id_demografia HAVING COUNT(*) > 1)
UNION ALL
SELECT 'hechos sin departamento', COUNT(*)
FROM hechos_suicidio h LEFT JOIN dim_departamento d ON h.cod_dpto = d.cod_dpto
WHERE d.cod_dpto IS NULL
UNION ALL
SELECT 'casos totales', SUM(casos) FROM hechos_suicidio;
