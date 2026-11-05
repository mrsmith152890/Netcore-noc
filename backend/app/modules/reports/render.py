import csv
import io
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings
from app.modules.alerts.engine import fmt_duration
from app.modules.reports.schema import Report

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")

def _tz(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y %H:%M")

def _num(v, decimals: int = 2, style: str = "es") -> str:
    if v is None:
        return ""
    s = f"{v:.{decimals}f}"
    return s.replace(".", ",") if style == "es" else s

def _safe(text: str) -> str:
    """Evita la inyección de fórmulas al abrir el CSV en Excel."""
    return "'" + text if text and text.startswith(_DANGEROUS) else text

# ---------- CSV ----------
def to_csv(report: Report, kind: str, style: str = "es") -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";" if style == "es" else ",", lineterminator="\r\n")
    if kind == "devices":
        w.writerow(["Dispositivo", "IP", "Sede", "Disponibilidad %", "Cobertura %", "Muestras",
                    "Fallidas", "Caídas", "Downtime estimado (s)", "RTT medio (ms)", "Pérdida media %"])
        for d in report.devices:
            w.writerow([_safe(d.name), d.ip, _safe(d.site), _num(d.availability_pct, 2, style),
                        _num(d.coverage_pct, 1, style), d.samples, d.failed, d.outages,
                        d.est_downtime_s, _num(d.avg_rtt_ms, 1, style), _num(d.avg_loss_pct, 2, style)])
    elif kind == "services":
        w.writerow(["Dispositivo", "Servicio", "Tipo", "Disponibilidad %", "Muestras", "Fallidas",
                    "Latencia media (ms)", "Latencia p95 (ms)"])
        for s in report.services:
            w.writerow([_safe(s.device), _safe(s.name), s.kind.upper(), _num(s.availability_pct, 2, style),
                        s.samples, s.failed, _num(s.avg_latency_ms, 1, style), _num(s.p95_latency_ms, 1, style)])
    else:
        w.writerow(["ID", "Dispositivo", "Regla", "Severidad", "Estado", "Inicio", "Fin", "Duración (s)", "Detalle"])
        for a in report.alert_rows:
            w.writerow([a.id, _safe(a.device), _safe(a.rule), a.severity, a.state, _tz(a.started_at),
                        _tz(a.ended_at) if a.ended_at else "", a.duration_s if a.duration_s is not None else "",
                        _safe(a.detail or "")])
    return "\ufeff" + buf.getvalue()      # BOM para que Excel reconozca UTF-8

# ---------- PDF ----------
def _table(header, rows, highlight: dict[int, colors.Color] | None = None) -> Table:
    t = Table([header] + rows, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9ca3af")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, color in (highlight or {}).items():
        style.append(("BACKGROUND", (0, i), (-1, i), color))
    t.setStyle(TableStyle(style))
    return t

def _row_color(avail: float | None):
    if avail is None:
        return None
    if avail < 99:
        return colors.HexColor("#fecaca")
    if avail < 99.9:
        return colors.HexColor("#fef3c7")
    return None

def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 0.8 * cm, f"Página {doc.page}")
    canvas.restoreState()

def to_pdf(report: Report) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Reporte de disponibilidad", author="NetCore NOC")
    styles = getSampleStyleSheet()
    p = report.period
    a = report.alerts
    story = [
        Paragraph("NetCore NOC — Reporte de disponibilidad", styles["Title"]),
        Paragraph(f"Periodo: {_tz(p.start)} a {_tz(p.end)} ({p.hours:.0f} h) · "
                  + (f"Sede: {escape(p.site)}" if p.site else "Todas las sedes"), styles["BodyText"]),
        Paragraph(f"Generado: {_tz(datetime.now(ZoneInfo(settings.timezone)))}", styles["BodyText"]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Disponibilidad media: <b>{_num(report.avg_availability_pct, 2) or '—'} %</b> · "
            f"Caídas: <b>{report.total_outages}</b> · Alertas: <b>{a.total}</b> "
            f"({a.critical} críticas, {a.warning} avisos) · "
            f"MTTR: <b>{fmt_duration(a.mttr_s) if a.mttr_s is not None else '—'}</b>", styles["BodyText"]),
        Spacer(1, 0.4 * cm),
        Paragraph("Dispositivos (ICMP)", styles["Heading2"]),
    ]

    devs = sorted(report.devices, key=lambda d: (d.availability_pct is None,
                                                  d.availability_pct if d.availability_pct is not None else 0))
    if devs:
        rows = [[d.name, d.ip, d.site, _num(d.availability_pct, 2) or "—", f"{d.coverage_pct:.0f} %",
                 d.outages, fmt_duration(d.est_downtime_s), _num(d.avg_rtt_ms, 1) or "—",
                 _num(d.avg_loss_pct, 2) or "—"] for d in devs]
        hl = {i + 1: _row_color(d.availability_pct) for i, d in enumerate(devs) if _row_color(d.availability_pct)}
        story.append(_table(["Dispositivo", "IP", "Sede", "Disp. %", "Cobertura", "Caídas",
                             "Downtime est.", "RTT (ms)", "Pérdida %"], rows, hl))
    else:
        story.append(Paragraph("Sin datos en el periodo.", styles["BodyText"]))

    story += [Spacer(1, 0.5 * cm), Paragraph("Servicios", styles["Heading2"])]
    svcs = sorted(report.services, key=lambda s: (s.availability_pct is None,
                                                   s.availability_pct if s.availability_pct is not None else 0))
    if svcs:
        rows = [[s.device, s.name, s.kind.upper(), _num(s.availability_pct, 2) or "—", s.samples, s.failed,
                 _num(s.avg_latency_ms, 1) or "—", _num(s.p95_latency_ms, 1) or "—"] for s in svcs]
        hl = {i + 1: _row_color(s.availability_pct) for i, s in enumerate(svcs) if _row_color(s.availability_pct)}
        story.append(_table(["Dispositivo", "Servicio", "Tipo", "Disp. %", "Muestras", "Fallidas",
                             "Latencia media (ms)", "Latencia p95 (ms)"], rows, hl))
    else:
        story.append(Paragraph("Sin comprobaciones de servicios en el periodo.", styles["BodyText"]))

    story += [Spacer(1, 0.5 * cm), Paragraph("Dispositivos con más alertas", styles["Heading2"])]
    if a.top_devices:
        story.append(_table(["Dispositivo", "Alertas"], [[t.device, t.alerts] for t in a.top_devices]))
    else:
        story.append(Paragraph("Sin alertas en el periodo.", styles["BodyText"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
