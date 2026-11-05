#!/usr/bin/env bash
# Resumen rápido durante una prueba de carga.
PSQL() { runuser -u postgres -- psql -d netcore "$@"; }
echo "== Latidos y duración del ciclo (cycle_ms debe ser MENOR que el intervalo) =="
PSQL -c "select worker, extract(epoch from now()-beat_at)::int as hace_s, cycle_ms, detail from worker_heartbeats order by worker"
echo "== Estados =="
PSQL -Atc "select 'dispositivos '||state||': '||count(*) from device_status group by state"
PSQL -Atc "select 'servicios '||state||': '||count(*) from service_status group by state"
echo "== Tablas que más crecen =="
PSQL -c "select relname, pg_size_pretty(pg_total_relation_size(oid)) as tamaño, reltuples::bigint as filas_aprox from pg_class where relname in ('ping_samples','interface_samples','device_metrics','service_results','audit_log') order by pg_total_relation_size(oid) desc"
echo "== Procesos del usuario netcore (CPU %, memoria KB) =="
ps -u netcore -o pid,pcpu,rss,etime,args --sort=-pcpu | head -8
echo "== Carga y memoria de la VM =="
uptime; free -m | head -2
