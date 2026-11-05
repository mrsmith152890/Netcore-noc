export interface AppBranding {
  logo_data: string | null
  favicon_data: string | null
  login_art_data: string | null
  login_status_enabled: boolean
}

export interface LoginNetworkSummary {
  enabled: boolean
  devices_total: number
  devices_up: number
  devices_down: number
  alerts_active: number
  alerts_critical: number
}

export type DeviceState = 'UP' | 'DOWN' | 'UNKNOWN'

export interface DeviceStatus {
  device_id: number
  site_id: number
  site_name: string
  name: string
  ip_address: string
  state: DeviceState
  consecutive_failures: number
  last_check_at: string | null
  last_rtt_ms: number | null
  last_change_at: string | null
  device_type: string
  wan_gateway_ip: string | null
  wan_probe_ip: string | null
  wan_gateway_state: DeviceState | null
  wan_gateway_rtt_ms: number | null
  wan_probe_state: DeviceState | null
  wan_probe_rtt_ms: number | null
  wan_checked_at: string | null
}

export interface PingSample { checked_at: string; success: boolean; rtt_ms: number | null; packet_loss: number }
export interface StatusEvent { at: string; from_state: string; to_state: string }

export interface InterfaceInfo {
  id: number
  if_index: number
  name: string | null
  descr: string | null
  speed_bps: number | null
  admin_status: string | null
  oper_status: string | null
  monitored: boolean
  in_bps: number | null
  out_bps: number | null
  last_sample_at: string | null
}

export interface InterfaceSample {
  sampled_at: string
  in_bps: number | null
  out_bps: number | null
  oper_status: string | null
}

export interface MetricSample {
  sampled_at: string
  cpu_pct: number | null
  mem_pct: number | null
  mem_used: number | null
  mem_total: number | null
}

export interface SnmpIdentity {
  device_id: number
  sys_name: string | null
  sys_descr: string | null
  uptime_s: number | null
  last_success_at: string | null
  last_error: string | null
}

export interface MapSummary {
  id: number
  name: string
  description: string | null
  domain_ids: number[]
  domain_names: string[]
  domain_id: number | null
  domain_name: string | null
  created_at: string
}

export interface MapNodeOut {
  id: number
  node_type: 'device' | 'label' | 'map' | 'ip'
  device_id: number | null
  label: string | null
  x: number
  y: number
  device_name: string | null
  device_ip: string | null
  device_type: string | null
  device_enabled: boolean | null
  ip_address: string | null
  discovery_source: string | null
  last_ping_ok: boolean | null
  last_snmp_ok: boolean | null
  last_arp_seen: boolean | null
  last_checked_at: string | null
  icon_data: string | null
  device_snmp_ok: boolean
  device_snmp_checked_at: string | null
  child_map_id: number | null
  child_map_name: string | null
  child_device_ids: number[]
}

export interface MapLinkOut {
  id: number
  source_node_id: number
  target_node_id: number
  source_handle: string | null
  target_handle: string | null
  label: string | null
}

export interface MapDetail extends MapSummary {
  nodes: MapNodeOut[]
  links: MapLinkOut[]
}

export interface SiteInfo {
  id: number
  name: string
  description: string | null
  enabled: boolean
  created_at?: string
  device_count: number
  scope_count: number
  rule_count: number
  silence_count: number
}

export interface DiscoveryScope {
  id: number
  site_id: number
  cidr: string
  description: string | null
  has_community: boolean
  snmp_port: number
  enabled: boolean
  allow_public: boolean
  created_at: string
}

export interface DiscoveryRun {
  id: number
  scope_id: number
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  created_at: string
  started_at: string | null
  finished_at: string | null
  hosts_total: number
  hosts_scanned: number
  hosts_alive: number
  hosts_snmp: number
  error: string | null
}

export interface DiscoveredHost {
  id: number
  run_id: number
  ip: string
  rtt_ms: number | null
  snmp_ok: boolean
  sys_name: string | null
  sys_descr: string | null
  sys_object_id: string | null
  vendor: string | null
  device_type: string
  device_id: number | null
  status: 'new' | 'registered' | 'imported'
}

export interface ImportResult {
  imported: number[]
  skipped: { host_id: number; reason: string }[]
}

export type Severity = 'warning' | 'critical'

export interface AlertOut {
  id: number
  rule_id: number
  rule_name: string
  rule_type: string
  severity: Severity
  state: 'pending' | 'firing' | 'acknowledged' | 'resolved'
  device_id: number
  device_name: string
  device_ip: string
  site_name: string
  created_at: string
  fired_at: string | null
  acked_at: string | null
  ack_note: string | null
  resolved_at: string | null
  resolution: string | null
  last_value: number | null
  escalated: boolean
  summary: string
}

export interface AlertRule {
  id: number
  name: string
  rule_type: string
  threshold: number | null
  for_seconds: number
  recover_after_s: number
  severity: Severity
  site_id: number | null
  device_id: number | null
  repeat_interval_s: number
  escalate_after_s: number | null
  enabled: boolean
}

export interface Channel {
  id: number
  name: string
  type: string
  min_severity: Severity
  enabled: boolean
  created_at: string
}

export interface Silence {
  id: number
  rule_id: number | null
  device_id: number | null
  site_id: number | null
  starts_at: string
  ends_at: string
  reason: string
  created_at: string
}

export interface NotificationLog {
  id: number
  alert_id: number | null
  channel_id: number
  kind: string
  status: 'pending' | 'sent' | 'failed' | 'suppressed'
  attempts: number
  created_at: string
  sent_at: string | null
  last_error: string | null
  text: string
}

export type Role = 'viewer' | 'operator' | 'admin'

export interface User {
  id: number
  username: string
  full_name: string | null
  role: Role
  enabled: boolean
  must_change_password: boolean
  locked_until: string | null
  last_login_at: string | null
  created_at: string
}

export interface AuditEntry {
  id: number
  at: string
  username: string | null
  ip: string | null
  method: string
  path: string
  status_code: number
  detail: string | null
}

export interface ServiceCheck {
  id: number
  device_id: number
  device_name: string
  name: string
  kind: 'tcp' | 'http' | 'dns'
  host: string | null
  port: number | null
  url: string | null
  expect_status: string | null
  expect_text: string | null
  verify_tls: boolean
  dns_query: string | null
  dns_type: string
  dns_expect: string | null
  interval_s: number
  timeout_s: number
  fail_threshold: number
  enabled: boolean
  state: 'UP' | 'DOWN' | 'UNKNOWN'
  consecutive_failures: number
  last_check_at: string | null
  last_latency_ms: number | null
  last_change_at: string | null
  last_error: string | null
}

export interface ServiceResult {
  checked_at: string
  success: boolean
  latency_ms: number | null
  error: string | null
}

export interface ReportDevice {
  device_id: number
  name: string
  ip: string
  site: string
  availability_pct: number | null
  coverage_pct: number
  samples: number
  failed: number
  outages: number
  est_downtime_s: number
  avg_rtt_ms: number | null
  avg_loss_pct: number | null
}

export interface ReportService {
  check_id: number
  device: string
  name: string
  kind: string
  availability_pct: number | null
  samples: number
  failed: number
  avg_latency_ms: number | null
  p95_latency_ms: number | null
}

export interface Report {
  period: { start: string; end: string; hours: number; site: string | null }
  avg_availability_pct: number | null
  total_outages: number
  devices: ReportDevice[]
  services: ReportService[]
  alerts: {
    total: number
    critical: number
    warning: number
    mttr_s: number | null
    top_devices: { device: string; alerts: number }[]
  }
}

export interface SystemStatus {
  overall_ok: boolean
  problems: number
  watchdog_ok: boolean
  watchdog_age_s: number | null
  checks: { key: string; title: string; ok: boolean; detail: string | null; since: string; checked_at: string }[]
  heartbeats: {
    worker: string
    title: string
    age_s: number | null
    expected_s: number
    ok: boolean
    cycle_ms: number | null
    detail: string | null
  }[]
}
