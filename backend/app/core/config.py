from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "NetCore NOC"
    environment: str = "dev"
    log_level: str = "INFO"
    timezone: str = "America/Bogota"
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str
    secret_key: str

    # Seguridad
    session_idle_hours: int = 12
    session_max_days: int = 7
    cookie_secure: bool = False        # pasar a true cuando haya HTTPS (Fase 10)
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    trust_proxy: bool = False          # true solo si la API únicamente es alcanzable por el proxy

    # Motor de disponibilidad (ICMP)
    probe_interval_s: int = 10
    ping_count: int = 3
    ping_timeout_s: int = 1
    fail_threshold: int = 3
    probe_concurrency: int = 50

    # SNMP
    snmp_interval_s: int = 60
    snmp_timeout_s: int = 2
    snmp_retries: int = 1
    snmp_walk_timeout_s: int = 30
    snmp_concurrency: int = 10

    # Descubrimiento
    discovery_allow_public: bool = False
    discovery_max_hosts: int = 1024
    discovery_concurrency: int = 100
    discovery_snmp_concurrency: int = 20
    discovery_ping_count: int = 2
    discovery_poll_interval_s: int = 3

    # Alertas
    alert_eval_interval_s: int = 15
    notify_max_attempts: int = 8

    # Comprobaciones de servicios
    service_tick_s: int = 5
    service_concurrency: int = 50

    # Retención de históricos (días)
    retention_ping_days: int = 45
    retention_interface_days: int = 90
    retention_metrics_days: int = 90
    retention_service_days: int = 90
    retention_events_days: int = 365
    retention_audit_days: int = 365
    retention_notifications_days: int = 90
    retention_alerts_days: int = 365
    retention_discovery_days: int = 60
    retention_batch_size: int = 20000

    # Vigilancia del sistema
    watchdog_interval_s: int = 30
    watchdog_confirm: int = 2
    watchdog_remind_s: int = 21600
    disk_warn_pct: int = 85
    cert_warn_days: int = 30
    heartbeat_url: str | None = None   # opcional: servicio externo que avisa si este sistema deja de latir

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOC_")

settings = Settings()
