import requests
import time
import logging
from datetime import datetime

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
API_KEY            = "0e6271615703dd0921b79da8260668f2"
HEADERS            = {"x-apisports-key": API_KEY}
INTERVALO_SEGUNDOS = 120   # cada 2 minutos

MINUTO_MINIMO      = 35
CORNERS_MINIMO     = 5
REMATES_PUERTA_MIN = 5

LIGAS_PERMITIDAS = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    2:   "Champions League",
    3:   "Europa League",
    848: "Europa Conference League",
    11:  "Copa Libertadores",
    13:  "Copa Sudamericana",
    253: "MLS",
    88:  "Eredivisie",
    94:  "Primeira Liga",
    203: "Süper Lig",
    307: "Saudi Pro League",
    144: "Pro League",
    119: "Superliga",
    113: "Allsvenskan",
    207: "Super League",
}

# ── Anti-duplicados: no alertar el mismo partido más de una vez ───────────────
ya_alertados = set()

# ══════════════════════════════════════════

def get_stat(estadisticas, nombre):
    for stat in estadisticas:
        if stat["type"] == nombre:
            val = stat["value"]
            if val is None:
                return 0
            if isinstance(val, str) and "%" in val:
                return val
            return int(val)
    return 0


def evaluar_partido(partido, stats):
    local       = partido["teams"]["home"]["name"]
    visita      = partido["teams"]["away"]["name"]
    liga_id     = partido["league"]["id"]
    liga_nombre = partido["league"]["name"]
    pais        = partido["league"]["country"]
    minuto      = partido["fixture"]["status"]["elapsed"] or 0
    goles_l     = partido["goals"]["home"] or 0
    goles_v     = partido["goals"]["away"] or 0

    resultado = {
        "fixture_id": partido["fixture"]["id"],
        "local":  local,
        "visita": visita,
        "liga":   liga_nombre,
        "pais":   pais,
        "minuto": minuto,
        "goles_l": goles_l,
        "goles_v": goles_v,
        "pasa_filtro": False,
        "razon_fallo": [],
    }

    if liga_id not in LIGAS_PERMITIDAS:
        resultado["razon_fallo"].append(f"Liga no monitoreada ({liga_nombre})")
        return resultado

    if goles_l != 0 or goles_v != 0:
        resultado["razon_fallo"].append(f"Hay goles ({goles_l}-{goles_v})")
        return resultado

    if minuto < MINUTO_MINIMO:
        resultado["razon_fallo"].append(f"Minuto insuficiente ({minuto} < {MINUTO_MINIMO})")
        return resultado

    if not stats:
        resultado["razon_fallo"].append("Sin estadísticas disponibles")
        return resultado

    stats_local  = stats[0]["statistics"]
    stats_visita = stats[1]["statistics"]

    corners_l  = get_stat(stats_local,  "Corner Kicks")
    corners_v  = get_stat(stats_visita, "Corner Kicks")
    puerta_l   = get_stat(stats_local,  "Shots on Goal")
    puerta_v   = get_stat(stats_visita, "Shots on Goal")
    total_l    = get_stat(stats_local,  "Total Shots")
    total_v    = get_stat(stats_visita, "Total Shots")
    poses_l    = get_stat(stats_local,  "Ball Possession")
    poses_v    = get_stat(stats_visita, "Ball Possession")
    atajadas_l = get_stat(stats_local,  "Goalkeeper Saves")
    atajadas_v = get_stat(stats_visita, "Goalkeeper Saves")
    tarjetas_l = get_stat(stats_local,  "Yellow Cards")
    tarjetas_v = get_stat(stats_visita, "Yellow Cards")

    total_corners = corners_l + corners_v
    total_puerta  = puerta_l  + puerta_v

    resultado.update({
        "corners_l":  corners_l,  "corners_v":  corners_v,
        "puerta_l":   puerta_l,   "puerta_v":   puerta_v,
        "total_l":    total_l,    "total_v":    total_v,
        "poses_l":    poses_l,    "poses_v":    poses_v,
        "atajadas_l": atajadas_l, "atajadas_v": atajadas_v,
        "tarjetas_l": tarjetas_l, "tarjetas_v": tarjetas_v,
    })

    if total_corners < CORNERS_MINIMO:
        resultado["razon_fallo"].append(f"Pocos corners ({total_corners} < {CORNERS_MINIMO})")

    if total_puerta < REMATES_PUERTA_MIN:
        resultado["razon_fallo"].append(f"Pocos remates a puerta ({total_puerta} < {REMATES_PUERTA_MIN})")

    if not resultado["razon_fallo"]:
        resultado["pasa_filtro"] = True

    return resultado


def enviar_alerta_telegram(r):
    """
    Rellena BOT_TOKEN y CHAT_ID para recibir alertas en Telegram.
    Déjalo vacío si no quieres notificaciones por ahora.
    """
    BOT_TOKEN = "8635706048:AAFKjArS1gCqKe1g9gvVy9bQCAPcIV_PH04"
    CHAT_ID   = "5723506255"

    if not BOT_TOKEN or not CHAT_ID:
        return

    texto = (
        f"🚨 *PARTIDO 0-0 CON PRESIÓN*\n\n"
        f"⚽ *{r['local']} 0 - 0 {r['visita']}*\n"
        f"🏆 {r['liga']} · {r['pais']}\n"
        f"⏱️ Minuto: {r['minuto']}\n\n"
        f"📊 *Estadísticas*\n"
        f"🎯 Remates: {r['total_l']} - {r['total_v']}\n"
        f"🟢 A puerta: {r['puerta_l']} - {r['puerta_v']}\n"
        f"🚩 Corners: {r['corners_l']} - {r['corners_v']}\n"
        f"🧤 Atajadas: {r['atajadas_l']} - {r['atajadas_v']}\n"
        f"🟨 Tarjetas: {r['tarjetas_l']} - {r['tarjetas_v']}\n"
        f"🤲 Posesión: {r['poses_l']} - {r['poses_v']}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "Markdown"
        }, timeout=10)
        log.info(f"✅ Alerta Telegram enviada: {r['local']} vs {r['visita']}")
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")


def ejecutar_ciclo():
    log.info("🔄 Revisando partidos en vivo...")

    try:
        url = "https://v3.football.api-sports.io/fixtures?live=all"
        r = requests.get(url, headers=HEADERS, timeout=10)
        partidos = r.json()["response"]
    except Exception as e:
        log.error(f"Error obteniendo partidos: {e}")
        return

    # ── Pre-filtro: solo ligas permitidas y marcador 0-0 ─────────────────────
    # Esto evita llamadas innecesarias a la API de estadísticas
    candidatos = [
        p for p in partidos
        if p["league"]["id"] in LIGAS_PERMITIDAS
        and (p["goals"]["home"] or 0) == 0
        and (p["goals"]["away"] or 0) == 0
        and (p["fixture"]["status"]["elapsed"] or 0) >= MINUTO_MINIMO
    ]

    log.info(f"📋 En vivo: {len(partidos)} | Candidatos tras pre-filtro: {len(candidatos)}")

    aprobados = 0

    for partido in candidatos:
        fixture_id = partido["fixture"]["id"]

        try:
            url_stats = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
            r2 = requests.get(url_stats, headers=HEADERS, timeout=10)
            stats = r2.json()["response"]
        except Exception as e:
            log.error(f"Error stats fixture {fixture_id}: {e}")
            continue

        resultado = evaluar_partido(partido, stats)

        if resultado["pasa_filtro"]:
            aprobados += 1
            log.info(
                f"🚨 {resultado['local']} vs {resultado['visita']} "
                f"| {resultado['liga']} | min {resultado['minuto']} "
                f"| corners {resultado['corners_l']+resultado['corners_v']} "
                f"| remates {resultado['puerta_l']+resultado['puerta_v']}"
            )

            # ── Solo alertar si no lo hemos notificado antes ─────────────────
            if fixture_id not in ya_alertados:
                ya_alertados.add(fixture_id)
                enviar_alerta_telegram(resultado)
        else:
            log.debug(f"  ✗ {resultado['local']} vs {resultado['visita']} → {' | '.join(resultado['razon_fallo'])}")

    log.info(f"✅ Aprobados: {aprobados} | Próxima revisión en {INTERVALO_SEGUNDOS}s\n")


def main():
    log.info("🚀 Monitor de fútbol iniciado")
    log.info(f"⚙️  Intervalo: {INTERVALO_SEGUNDOS}s | Min: {MINUTO_MINIMO} | Corners: {CORNERS_MINIMO} | Remates: {REMATES_PUERTA_MIN}")

    while True:
        ejecutar_ciclo()
        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
