"""
================================================================================
FGO — GA4 Analytics Runner (Standalone)
================================================================================
Extrage date din Google Analytics 4 Data API (REST) si le exporta
in dashboard_data.js pentru afisare in dashboard.html.

Foloseste OAuth2 cu aceleasi credentiale din config_api.ini
(client_id, client_secret) + un refresh_token GA4 separat.

Datasets generate:
  DS1: Funnel de conversie in-app iOS (zilnic)
  DS2: Engagement & sesiuni (zilnic, cross-platform)
  DS3: Feature usage + error rates iOS (zilnic)
  DS4: Distributie abonamente iOS per tier (zilnic)
  DS5: Sumar KPI-uri GA4 iOS (o singura linie)
  DS6: Funnel de conversie in-app Android (zilnic)
  DS7: Feature usage + error rates Android (zilnic)
  DS8: Distributie abonamente Android per tier (zilnic)
  DS9: Sumar KPI-uri GA4 Android (o singura linie)
  DS10: Funnel de conversie Web (zilnic)

Utilizare:
    python run_GA4.py                  # toate dataseturile
    python run_GA4.py funnel           # doar funnel iOS
    python run_GA4.py engagement       # doar engagement (cross-platform)
    python run_GA4.py features         # doar feature usage iOS
    python run_GA4.py abonamente       # doar distributie abonamente iOS
    python run_GA4.py funnel_android   # doar funnel Android
    python run_GA4.py features_android # doar feature usage Android
    python run_GA4.py web              # doar funnel Web

Prerequisite:
    pip install requests
    Refresh token cu scope analytics.readonly (vezi get_ga4_refresh_token.py)

Versiune: 1.0
Data: 2026-03-30
Autor: Valeriu Filip / Claude
================================================================================
"""

import sys
import json
import csv
import requests
from pathlib import Path
from datetime import datetime, timedelta

# ============================================================================
# CONFIGURARE
# ============================================================================
SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_ga4, ConfigError  # noqa: E402

OUTPUT_DIR = SCRIPT_DIR / "rezultate"

# Google OAuth - URL fix, property-specific URL se construieste runtime din config
TOKEN_URL = "https://oauth2.googleapis.com/token"
GA4_API_BASE_TEMPLATE = "https://analyticsdata.googleapis.com/{version}/properties/{property_id}"

# Variabile globale populate la runtime din config/ga4.ini (sectiunea [ga4])
GA4_PROPERTY_ID: str = ""
GA4_API_BASE: str = ""

# Evenimente FGO custom — grupate logic
FUNNEL_EVENTS = [
    "first_open",
    "creare_cont_ios",
    "Ecran_abonament_ios",
    "ecran_abonament_ios",
    "tapped_ab_efactura_ios",
    "tapped_ab_premium_ios",
    "tapped_ab_enterprise_ios",
    "Cumpara_abonament_tapped",
]

FEATURE_EVENTS = [
    "creare_factura_ios",
    "modificare_factura_ios",
    "acceptare_factura_furnizor_ios",
    "respingere_factura_furnizor_ios",
    "creare_comanda_ios",
    "modificare_comanda_ios",
    "eroare_creare_factura_ios",
    "eroare_modificare_factura_ios",
    "eroare_creare_comanda_ios",
    "eroare_modificare_comanda_ios",
    "eroare_creare_cont_ios",
]

ENGAGEMENT_EVENTS = [
    "session_start",
    "user_engagement",
    "screen_view",
    "Ecrane_accesate_iOS",
    "app_update",
    "first_open",
    "notification_open",
]

SUBSCRIPTION_EVENTS = [
    "abonament_ios_free",
    "abonament_ios_efactura",
    "abonament_ios_premium",
    "abonament_ios_enterprise",
    "abonament_ios_pro",
]

# ============================================================================
# ANDROID EVENTS (mirroring iOS structure)
# ============================================================================
FUNNEL_EVENTS_ANDROID = [
    "first_open",
    "creare_cont_android",
    "ecran_abonament_android",
    "Ecran_abonament_android",
    "tapped_ab_efactura_android",
    "tapped_ab_premium_android",
    "tapped_ab_enterprise_android",
]

FEATURE_EVENTS_ANDROID = [
    "creare_factura_android",
    "modificare_factura_android",
    "acceptare_factura_furnizor_android",
    "respingere_factura_furnizor_android",
    "creare_comanda_android",
    "modificare_comanda_android",
    "eroare_creare_factura_android",
    "eroare_modificare_factura_android",
    "eroare_creare_comanda_android",
    "eroare_modificare_comanda_android",
    "eroare_creare_cont_android",
]

ENGAGEMENT_EVENTS_ANDROID = [
    "session_start",
    "user_engagement",
    "screen_view",
    "Ecrane_accesate_android",
    "app_update",
    "first_open",
    "notification_open",
]

SUBSCRIPTION_EVENTS_ANDROID = [
    "abonament_android_free",
    "abonament_android_efactura",
    "abonament_android_premium",
    "abonament_android_enterprise",
    "abonament_android_pro",
]

# ============================================================================
# WEB EVENTS (limited set)
# ============================================================================
WEB_EVENTS = [
    "registration_started",
    "registration_free",
    "vizualizare_pagina_stocuri",
    "page_view",
    "first_visit",
    "scroll",
    "form_start",
    "form_submit",
    "click",
    "file_download",
    "view_search_results",
]


# ============================================================================
# OAUTH2 — Access Token din Refresh Token
# ============================================================================
def get_access_token(config):
    """Obtine access token GA4 folosind credentialele din sectiunea [ga4].

    Nu mai facem fallback pe [google_ads] — GA4 are nevoie de scope
    analytics.readonly, care nu exista in refresh_token-ul Google Ads.
    """
    g = config["ga4"]
    required = ("client_id", "client_secret", "refresh_token")
    missing = [k for k in required if not g.get(k, "").strip().strip('"')]
    if missing:
        print(f"[!] Lipsesc in [ga4]: {', '.join(missing)}")
        print("    Ruleaza: python get_ga4_refresh_token.py pentru a le completa")
        sys.exit(1)

    client_id = g.get("client_id").strip().strip('"')
    client_secret = g.get("client_secret").strip().strip('"')
    refresh_token = g.get("refresh_token").strip().strip('"')

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })

    if resp.status_code != 200:
        raise Exception(f"OAuth token error ({resp.status_code}): {resp.text}")

    token = resp.json().get("access_token")
    if not token:
        raise Exception(f"Nu am primit access_token: {resp.json()}")

    print(f"  [OK] Access token obtinut ({len(token)} chars)")
    return token


# ============================================================================
# GA4 DATA API — Executie rapoarte
# ============================================================================
def run_ga4_report(access_token, date_ranges, dimensions, metrics,
                   dimension_filter=None, order_bys=None, limit=10000):
    """
    Apeleaza GA4 Data API v1beta :runReport.
    Returneaza lista de dict-uri cu datele.
    """
    url = f"{GA4_API_BASE}:runReport"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    body = {
        "dateRanges": date_ranges,
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }

    if dimension_filter:
        body["dimensionFilter"] = dimension_filter

    if order_bys:
        body["orderBys"] = order_bys

    resp = requests.post(url, headers=headers, json=body)

    if resp.status_code != 200:
        error_detail = resp.text[:500]
        raise Exception(f"GA4 API error ({resp.status_code}): {error_detail}")

    data = resp.json()
    rows = data.get("rows", [])

    # Convertim in list of dicts
    dim_headers = [h["name"] for h in data.get("dimensionHeaders", [])]
    met_headers = [h["name"] for h in data.get("metricHeaders", [])]

    result = []
    for row in rows:
        d = {}
        for i, dim in enumerate(row.get("dimensionValues", [])):
            d[dim_headers[i]] = dim["value"]
        for i, met in enumerate(row.get("metricValues", [])):
            d[met_headers[i]] = met["value"]
        result.append(d)

    return result


def make_event_filter(event_names):
    """Creeaza un dimensionFilter pentru o lista de eventName-uri."""
    return {
        "filter": {
            "fieldName": "eventName",
            "inListFilter": {
                "values": event_names
            }
        }
    }


# ============================================================================
# DATASET BUILDERS
# ============================================================================
def build_ds1_funnel(access_token, start_date, end_date):
    """
    DS1: Funnel de conversie in-app — evolutie zilnica.
    Grupam evenimentele pe etape: first_open, creare_cont, ecran_abonament,
    tapped_ab.
    """
    print("  [DS1] Funnel de conversie in-app...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Luam eventCount + totalUsers per eventName per zi
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FUNNEL_EVENTS),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    # Agregam pe zile si etape funnel
    days = {}
    for r in raw:
        day = r["date"]  # YYYYMMDD
        evt = r["eventName"]
        count = int(r["eventCount"])
        users = int(r["totalUsers"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "first_open": 0, "first_open_users": 0,
                "creare_cont": 0, "creare_cont_users": 0,
                "ecran_abonament": 0, "ecran_abonament_users": 0,
                "tapped_abonament": 0, "tapped_abonament_users": 0,
            }

        d = days[day]
        if evt == "first_open":
            d["first_open"] += count
            d["first_open_users"] += users
        elif evt == "creare_cont_ios":
            d["creare_cont"] += count
            d["creare_cont_users"] += users
        elif evt in ("ecran_abonament_ios", "Ecran_abonament_ios"):
            d["ecran_abonament"] += count
            d["ecran_abonament_users"] += users
        elif evt in ("tapped_ab_efactura_ios", "tapped_ab_premium_ios",
                      "tapped_ab_enterprise_ios", "Cumpara_abonament_tapped"):
            d["tapped_abonament"] += count
            d["tapped_abonament_users"] += users

    result = sorted(days.values(), key=lambda x: x["data"])
    print(f"    -> {len(result)} zile, {len(raw)} raw rows")
    return result


def build_ds1_funnel_android(access_token, start_date, end_date):
    """
    DS6: Funnel de conversie in-app (Android) — evolutie zilnica.
    Grupam evenimentele pe etape: first_open, creare_cont, ecran_abonament,
    tapped_ab.
    """
    print("  [DS6] Funnel de conversie in-app (Android)...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Luam eventCount + totalUsers per eventName per zi
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FUNNEL_EVENTS_ANDROID),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    # Agregam pe zile si etape funnel
    days = {}
    for r in raw:
        day = r["date"]  # YYYYMMDD
        evt = r["eventName"]
        count = int(r["eventCount"])
        users = int(r["totalUsers"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "first_open": 0, "first_open_users": 0,
                "creare_cont": 0, "creare_cont_users": 0,
                "ecran_abonament": 0, "ecran_abonament_users": 0,
                "tapped_abonament": 0, "tapped_abonament_users": 0,
            }

        d = days[day]
        if evt == "first_open":
            d["first_open"] += count
            d["first_open_users"] += users
        elif evt == "creare_cont_android":
            d["creare_cont"] += count
            d["creare_cont_users"] += users
        elif evt in ("ecran_abonament_android", "Ecran_abonament_android"):
            d["ecran_abonament"] += count
            d["ecran_abonament_users"] += users
        elif evt in ("tapped_ab_efactura_android", "tapped_ab_premium_android",
                      "tapped_ab_enterprise_android"):
            d["tapped_abonament"] += count
            d["tapped_abonament_users"] += users

    result = sorted(days.values(), key=lambda x: x["data"])
    print(f"    -> {len(result)} zile, {len(raw)} raw rows")
    return result


def build_ds2_engagement(access_token, start_date, end_date):
    """
    DS2: Engagement zilnic — sesiuni, user_engagement, screen_view,
    active users, sessions per user.
    """
    print("  [DS2] Engagement & sesiuni zilnice...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Raport 1: metrici agregate per zi
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date"],
        metrics=["activeUsers", "sessions", "screenPageViews",
                 "userEngagementDuration", "sessionsPerUser",
                 "engagedSessions", "engagementRate"],
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    result = []
    for r in raw:
        day = r["date"]
        result.append({
            "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
            "active_users": r.get("activeUsers", "0"),
            "sessions": r.get("sessions", "0"),
            "screen_views": r.get("screenPageViews", "0"),
            "engagement_duration_sec": r.get("userEngagementDuration", "0"),
            "sessions_per_user": r.get("sessionsPerUser", "0"),
            "engaged_sessions": r.get("engagedSessions", "0"),
            "engagement_rate": r.get("engagementRate", "0"),
        })

    print(f"    -> {len(result)} zile")
    return result


def build_ds3_features(access_token, start_date, end_date):
    """
    DS3: Feature usage + error rates — zilnic per functionalitate.
    """
    print("  [DS3] Feature usage + error rates...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FEATURE_EVENTS),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    # Agregam pe zile
    days = {}
    for r in raw:
        day = r["date"]
        evt = r["eventName"]
        count = int(r["eventCount"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "creare_factura": 0, "modificare_factura": 0,
                "acceptare_factura": 0, "respingere_factura": 0,
                "creare_comanda": 0, "modificare_comanda": 0,
                "err_creare_factura": 0, "err_modificare_factura": 0,
                "err_creare_comanda": 0, "err_modificare_comanda": 0,
                "err_creare_cont": 0,
            }

        d = days[day]
        mapping = {
            "creare_factura_ios": "creare_factura",
            "modificare_factura_ios": "modificare_factura",
            "acceptare_factura_furnizor_ios": "acceptare_factura",
            "respingere_factura_furnizor_ios": "respingere_factura",
            "creare_comanda_ios": "creare_comanda",
            "modificare_comanda_ios": "modificare_comanda",
            "eroare_creare_factura_ios": "err_creare_factura",
            "eroare_modificare_factura_ios": "err_modificare_factura",
            "eroare_creare_comanda_ios": "err_creare_comanda",
            "eroare_modificare_comanda_ios": "err_modificare_comanda",
            "eroare_creare_cont_ios": "err_creare_cont",
        }
        col = mapping.get(evt)
        if col:
            d[col] += count

    result = sorted(days.values(), key=lambda x: x["data"])

    # Adaugam rate de eroare calculate
    for r in result:
        total_facturi = r["creare_factura"] + r["modificare_factura"]
        total_err_facturi = r["err_creare_factura"] + r["err_modificare_factura"]
        r["rata_eroare_facturi"] = round(total_err_facturi / total_facturi * 100, 2) if total_facturi > 0 else 0

        total_comenzi = r["creare_comanda"] + r["modificare_comanda"]
        total_err_comenzi = r["err_creare_comanda"] + r["err_modificare_comanda"]
        r["rata_eroare_comenzi"] = round(total_err_comenzi / total_comenzi * 100, 2) if total_comenzi > 0 else 0

    print(f"    -> {len(result)} zile")
    return result


def build_ds3_features_android(access_token, start_date, end_date):
    """
    DS7: Feature usage + error rates (Android) — zilnic per functionalitate.
    """
    print("  [DS7] Feature usage + error rates (Android)...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FEATURE_EVENTS_ANDROID),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    # Agregam pe zile
    days = {}
    for r in raw:
        day = r["date"]
        evt = r["eventName"]
        count = int(r["eventCount"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "creare_factura": 0, "modificare_factura": 0,
                "acceptare_factura": 0, "respingere_factura": 0,
                "creare_comanda": 0, "modificare_comanda": 0,
                "err_creare_factura": 0, "err_modificare_factura": 0,
                "err_creare_comanda": 0, "err_modificare_comanda": 0,
                "err_creare_cont": 0,
            }

        d = days[day]
        mapping = {
            "creare_factura_android": "creare_factura",
            "modificare_factura_android": "modificare_factura",
            "acceptare_factura_furnizor_android": "acceptare_factura",
            "respingere_factura_furnizor_android": "respingere_factura",
            "creare_comanda_android": "creare_comanda",
            "modificare_comanda_android": "modificare_comanda",
            "eroare_creare_factura_android": "err_creare_factura",
            "eroare_modificare_factura_android": "err_modificare_factura",
            "eroare_creare_comanda_android": "err_creare_comanda",
            "eroare_modificare_comanda_android": "err_modificare_comanda",
            "eroare_creare_cont_android": "err_creare_cont",
        }
        col = mapping.get(evt)
        if col:
            d[col] += count

    result = sorted(days.values(), key=lambda x: x["data"])

    # Adaugam rate de eroare calculate
    for r in result:
        total_facturi = r["creare_factura"] + r["modificare_factura"]
        total_err_facturi = r["err_creare_factura"] + r["err_modificare_factura"]
        r["rata_eroare_facturi"] = round(total_err_facturi / total_facturi * 100, 2) if total_facturi > 0 else 0

        total_comenzi = r["creare_comanda"] + r["modificare_comanda"]
        total_err_comenzi = r["err_creare_comanda"] + r["err_modificare_comanda"]
        r["rata_eroare_comenzi"] = round(total_err_comenzi / total_comenzi * 100, 2) if total_comenzi > 0 else 0

    print(f"    -> {len(result)} zile")
    return result


def build_ds4_subscriptions(access_token, start_date, end_date):
    """
    DS4: Distributie abonamente per tier — evolutie zilnica.
    """
    print("  [DS4] Distributie abonamente per tier...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(SUBSCRIPTION_EVENTS),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    days = {}
    for r in raw:
        day = r["date"]
        evt = r["eventName"]
        count = int(r["eventCount"])
        users = int(r["totalUsers"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "free_count": 0, "free_users": 0,
                "efactura_count": 0, "efactura_users": 0,
                "premium_count": 0, "premium_users": 0,
                "enterprise_count": 0, "enterprise_users": 0,
                "pro_count": 0, "pro_users": 0,
                "total_count": 0, "total_users": 0,
            }

        d = days[day]
        tier_map = {
            "abonament_ios_free": "free",
            "abonament_ios_efactura": "efactura",
            "abonament_ios_premium": "premium",
            "abonament_ios_enterprise": "enterprise",
            "abonament_ios_pro": "pro",
        }
        tier = tier_map.get(evt)
        if tier:
            d[f"{tier}_count"] += count
            d[f"{tier}_users"] += users
            d["total_count"] += count
            d["total_users"] += users

    result = sorted(days.values(), key=lambda x: x["data"])
    print(f"    -> {len(result)} zile")
    return result


def build_ds4_subscriptions_android(access_token, start_date, end_date):
    """
    DS8: Distributie abonamente per tier (Android) — evolutie zilnica.
    """
    print("  [DS8] Distributie abonamente per tier (Android)...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(SUBSCRIPTION_EVENTS_ANDROID),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    days = {}
    for r in raw:
        day = r["date"]
        evt = r["eventName"]
        count = int(r["eventCount"])
        users = int(r["totalUsers"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "free_count": 0, "free_users": 0,
                "efactura_count": 0, "efactura_users": 0,
                "premium_count": 0, "premium_users": 0,
                "enterprise_count": 0, "enterprise_users": 0,
                "pro_count": 0, "pro_users": 0,
                "total_count": 0, "total_users": 0,
            }

        d = days[day]
        tier_map = {
            "abonament_android_free": "free",
            "abonament_android_efactura": "efactura",
            "abonament_android_premium": "premium",
            "abonament_android_enterprise": "enterprise",
            "abonament_android_pro": "pro",
        }
        tier = tier_map.get(evt)
        if tier:
            d[f"{tier}_count"] += count
            d[f"{tier}_users"] += users
            d["total_count"] += count
            d["total_users"] += users

    result = sorted(days.values(), key=lambda x: x["data"])
    print(f"    -> {len(result)} zile")
    return result


def build_ds5_summary(access_token, start_date, end_date):
    """
    DS5: KPI-uri sumare GA4 (o singura linie) — pentru cardurile din dashboard.
    """
    print("  [DS5] Sumar KPI-uri GA4...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Metrici globale
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=[],
        metrics=["activeUsers", "newUsers", "totalUsers", "sessions",
                 "screenPageViews", "userEngagementDuration",
                 "sessionsPerUser", "engagementRate", "engagedSessions"],
    )

    summary = raw[0] if raw else {}

    # Funnel totals
    funnel_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FUNNEL_EVENTS),
    )

    funnel_totals = {}
    for r in funnel_raw:
        funnel_totals[r["eventName"]] = {
            "count": int(r["eventCount"]),
            "users": int(r["totalUsers"]),
        }

    # Calcule funnel
    first_open = funnel_totals.get("first_open", {}).get("users", 0)
    creare_cont = funnel_totals.get("creare_cont_ios", {}).get("users", 0)

    ecran_ab = (funnel_totals.get("ecran_abonament_ios", {}).get("users", 0) +
                funnel_totals.get("Ecran_abonament_ios", {}).get("users", 0))

    tapped = sum(funnel_totals.get(e, {}).get("users", 0) for e in [
        "tapped_ab_efactura_ios", "tapped_ab_premium_ios",
        "tapped_ab_enterprise_ios", "Cumpara_abonament_tapped"])

    # Error totals
    err_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount"],
        dimension_filter=make_event_filter([e for e in FEATURE_EVENTS if e.startswith("eroare_")]),
    )
    total_errors = sum(int(r["eventCount"]) for r in err_raw)

    feat_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount"],
        dimension_filter=make_event_filter([e for e in FEATURE_EVENTS if not e.startswith("eroare_")]),
    )
    total_actions = sum(int(r["eventCount"]) for r in feat_raw)

    result = [{
        "perioada": f"{start_date} — {end_date}",
        "total_users": summary.get("totalUsers", "0"),
        "active_users": summary.get("activeUsers", "0"),
        "new_users": summary.get("newUsers", "0"),
        "sessions": summary.get("sessions", "0"),
        "screen_views": summary.get("screenPageViews", "0"),
        "engagement_rate": summary.get("engagementRate", "0"),
        "sessions_per_user": summary.get("sessionsPerUser", "0"),
        "engagement_duration_sec": summary.get("userEngagementDuration", "0"),
        # Funnel
        "funnel_first_open": str(first_open),
        "funnel_creare_cont": str(creare_cont),
        "funnel_ecran_abonament": str(ecran_ab),
        "funnel_tapped": str(tapped),
        "funnel_conv_rate": str(round(tapped / first_open * 100, 2) if first_open > 0 else 0),
        # Errors
        "total_actions": str(total_actions),
        "total_errors": str(total_errors),
        "error_rate": str(round(total_errors / total_actions * 100, 2) if total_actions > 0 else 0),
    }]

    print(f"    -> 1 linie sumar ({summary.get('activeUsers','?')} active users)")
    return result


def build_ds5_summary_android(access_token, start_date, end_date):
    """
    DS9: KPI-uri sumare GA4 (Android) (o singura linie) — pentru cardurile din dashboard.
    """
    print("  [DS9] Sumar KPI-uri GA4 (Android)...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Metrici globale
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=[],
        metrics=["activeUsers", "newUsers", "totalUsers", "sessions",
                 "screenPageViews", "userEngagementDuration",
                 "sessionsPerUser", "engagementRate", "engagedSessions"],
    )

    summary = raw[0] if raw else {}

    # Funnel totals
    funnel_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(FUNNEL_EVENTS_ANDROID),
    )

    funnel_totals = {}
    for r in funnel_raw:
        funnel_totals[r["eventName"]] = {
            "count": int(r["eventCount"]),
            "users": int(r["totalUsers"]),
        }

    # Calcule funnel
    first_open = funnel_totals.get("first_open", {}).get("users", 0)
    creare_cont = funnel_totals.get("creare_cont_android", {}).get("users", 0)

    ecran_ab = (funnel_totals.get("ecran_abonament_android", {}).get("users", 0) +
                funnel_totals.get("Ecran_abonament_android", {}).get("users", 0))

    tapped = sum(funnel_totals.get(e, {}).get("users", 0) for e in [
        "tapped_ab_efactura_android", "tapped_ab_premium_android",
        "tapped_ab_enterprise_android"])

    # Error totals
    err_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount"],
        dimension_filter=make_event_filter([e for e in FEATURE_EVENTS_ANDROID if e.startswith("eroare_")]),
    )
    total_errors = sum(int(r["eventCount"]) for r in err_raw)

    feat_raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["eventName"],
        metrics=["eventCount"],
        dimension_filter=make_event_filter([e for e in FEATURE_EVENTS_ANDROID if not e.startswith("eroare_")]),
    )
    total_actions = sum(int(r["eventCount"]) for r in feat_raw)

    result = [{
        "perioada": f"{start_date} — {end_date}",
        "total_users": summary.get("totalUsers", "0"),
        "active_users": summary.get("activeUsers", "0"),
        "new_users": summary.get("newUsers", "0"),
        "sessions": summary.get("sessions", "0"),
        "screen_views": summary.get("screenPageViews", "0"),
        "engagement_rate": summary.get("engagementRate", "0"),
        "sessions_per_user": summary.get("sessionsPerUser", "0"),
        "engagement_duration_sec": summary.get("userEngagementDuration", "0"),
        # Funnel
        "funnel_first_open": str(first_open),
        "funnel_creare_cont": str(creare_cont),
        "funnel_ecran_abonament": str(ecran_ab),
        "funnel_tapped": str(tapped),
        "funnel_conv_rate": str(round(tapped / first_open * 100, 2) if first_open > 0 else 0),
        # Errors
        "total_actions": str(total_actions),
        "total_errors": str(total_errors),
        "error_rate": str(round(total_errors / total_actions * 100, 2) if total_actions > 0 else 0),
    }]

    print(f"    -> 1 linie sumar ({summary.get('activeUsers','?')} active users)")
    return result


def build_web_ds1(access_token, start_date, end_date):
    """
    DS10: Funnel de conversie Web — evolutie zilnica.
    Web events: registration_started, registration_free, form_start, form_submit.
    """
    print("  [DS10] Funnel de conversie Web...")

    date_ranges = [{"startDate": start_date, "endDate": end_date}]

    # Luam eventCount + totalUsers per eventName per zi
    raw = run_ga4_report(
        access_token, date_ranges,
        dimensions=["date", "eventName"],
        metrics=["eventCount", "totalUsers"],
        dimension_filter=make_event_filter(WEB_EVENTS),
        order_bys=[{"dimension": {"dimensionName": "date"}}],
    )

    # Agregam pe zile si etape funnel
    days = {}
    for r in raw:
        day = r["date"]  # YYYYMMDD
        evt = r["eventName"]
        count = int(r["eventCount"])
        users = int(r["totalUsers"])

        if day not in days:
            days[day] = {
                "data": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                "registration_started": 0, "registration_started_users": 0,
                "registration_free": 0, "registration_free_users": 0,
                "form_start": 0, "form_start_users": 0,
                "form_submit": 0, "form_submit_users": 0,
                "page_views": 0, "page_views_users": 0,
                "first_visit": 0, "first_visit_users": 0,
            }

        d = days[day]
        if evt == "registration_started":
            d["registration_started"] += count
            d["registration_started_users"] += users
        elif evt == "registration_free":
            d["registration_free"] += count
            d["registration_free_users"] += users
        elif evt == "form_start":
            d["form_start"] += count
            d["form_start_users"] += users
        elif evt == "form_submit":
            d["form_submit"] += count
            d["form_submit_users"] += users
        elif evt == "page_view":
            d["page_views"] += count
            d["page_views_users"] += users
        elif evt == "first_visit":
            d["first_visit"] += count
            d["first_visit_users"] += users

    result = sorted(days.values(), key=lambda x: x["data"])
    print(f"    -> {len(result)} zile, {len(raw)} raw rows")
    return result


# ============================================================================
# EXPORT + MERGE
# ============================================================================
DATASET_BUILDERS = [
    # iOS datasets (original, backward compatible)
    ("funnel",               1, "Funnel conversie in-app iOS (zilnic)", build_ds1_funnel),
    ("engagement",           2, "Engagement & sesiuni (zilnic)", build_ds2_engagement),
    ("features",             3, "Feature usage + error rates iOS (zilnic)", build_ds3_features),
    ("abonamente",           4, "Distributie abonamente iOS per tier (zilnic)", build_ds4_subscriptions),
    ("summary",              5, "Sumar KPI-uri GA4 iOS", build_ds5_summary),

    # Android datasets (new)
    ("funnel_android",       6, "Funnel conversie in-app Android (zilnic)", build_ds1_funnel_android),
    ("features_android",     7, "Feature usage + error rates Android (zilnic)", build_ds3_features_android),
    ("abonamente_android",   8, "Distributie abonamente Android per tier (zilnic)", build_ds4_subscriptions_android),
    ("summary_android",      9, "Sumar KPI-uri GA4 Android", build_ds5_summary_android),

    # Web dataset (new)
    ("web",                 10, "Funnel conversie Web (zilnic)", build_web_ds1),
]


def export_csv(data, columns, filename):
    """Exporta un dataset in CSV."""
    csv_path = OUTPUT_DIR / filename
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)
    print(f"    -> CSV: {filename} ({len(data)} randuri)")
    return csv_path


def merge_dashboard_data(datasets):
    """
    Citeste dashboard_data.js existent, inlocuieste/extinde prefixul 'ga4',
    pastreaza celelalte scripturi intacte.
    Merge datasets de la iOS, Android si Web intr-un singur entry 'ga4'.
    """
    js_path = OUTPUT_DIR / "dashboard_data.js"
    existing_obj = None

    if js_path.exists():
        try:
            text = js_path.read_text(encoding='utf-8')
            start = text.index('{')
            end = text.rindex('}') + 1
            existing_obj = json.loads(text[start:end])
            print(f"[i] Dashboard existent citit: {len(existing_obj.get('scripts',[]))} scripturi")
        except Exception as e:
            print(f"[!] Nu am putut citi dashboard_data.js existent: {e}")
            existing_obj = None

    if existing_obj is None:
        existing_obj = {'generated_at': datetime.now().isoformat(), 'scripts': []}

    # Pastram tot mai putin 'ga4'
    kept_scripts = [s for s in existing_obj.get('scripts', []) if s.get('prefix') != 'ga4']

    # Construim script entry GA4
    ga4_script = {
        'script': 'GA4_Analytics_iOS.py',
        'description': 'Google Analytics 4 — FGO iOS App',
        'prefix': 'ga4',
        'status': 'OK',
        'datasets': datasets,
    }
    kept_scripts.append(ga4_script)

    existing_obj['scripts'] = kept_scripts
    existing_obj['generated_at'] = datetime.now().isoformat()

    with open(js_path, 'w', encoding='utf-8') as f:
        f.write("// Auto-generated by run_analiza.py — NU edita manual\n")
        f.write(f"// Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("window.DASHBOARD = ")
        json.dump(existing_obj, f, ensure_ascii=False, indent=None)
        f.write(";\n")

    size_kb = js_path.stat().st_size / 1024
    print(f"[OK] Dashboard data MERGED: {js_path} ({size_kb:.0f} KB) — {len(kept_scripts)} scripturi total")


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 60)
    print(" FGO — GA4 Analytics (iOS, Android, Web)")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Citire config GA4 (config/ga4.ini)
    try:
        config = load_ga4()
    except ConfigError as e:
        print(f"[!] {e}")
        sys.exit(1)

    # Populam globals din config
    global GA4_PROPERTY_ID, GA4_API_BASE
    GA4_PROPERTY_ID = config["ga4"].get("property_id", "").strip()
    api_version = config["ga4"].get("api_version", "v1beta").strip() or "v1beta"
    if not GA4_PROPERTY_ID or GA4_PROPERTY_ID == "0":
        print("[!] property_id lipseste din config/ga4.ini [ga4]")
        sys.exit(1)
    GA4_API_BASE = GA4_API_BASE_TEMPLATE.format(version=api_version, property_id=GA4_PROPERTY_ID)

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Parametri
    args = sys.argv[1:]
    filter_name = args[0].lower() if args else None

    # Perioada: default ultimele 30 zile
    zile_input = input("\n  Nr zile analiza GA4 [default=30]: ").strip()
    nr_zile = int(zile_input) if zile_input.isdigit() and int(zile_input) > 0 else 30

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=nr_zile)).strftime("%Y-%m-%d")

    print(f"\n  Perioada: {start_date} — {end_date} ({nr_zile} zile)")
    print(f"  Property: {GA4_PROPERTY_ID}")

    # OAuth
    print(f"\n[AUTH] Obtinere access token...")
    access_token = get_access_token(config)

    # Selectie datasets
    builders_to_run = DATASET_BUILDERS
    if filter_name:
        builders_to_run = [b for b in DATASET_BUILDERS if filter_name in b[0]]
        if not builders_to_run:
            print(f"[!] Niciun dataset gasit pentru '{filter_name}'")
            print(f"    iOS: funnel, features, abonamente, summary, engagement")
            print(f"    Android: funnel_android, features_android, abonamente_android, summary_android")
            print(f"    Web: web")
            sys.exit(1)

    print(f"\n  Datasets de extras: {len(builders_to_run)}")
    for name, idx, desc, _ in builders_to_run:
        print(f"    DS{idx}: {desc}")

    # Executie
    all_datasets = []
    for name, idx, desc, builder_fn in builders_to_run:
        try:
            data = builder_fn(access_token, start_date, end_date)

            if data:
                columns = list(data[0].keys())

                # Export CSV
                csv_name = f"ga4_ds{idx}.csv"
                export_csv(data, columns, csv_name)

                all_datasets.append({
                    'name': f"ga4_ds{idx}",
                    'dataset_index': idx,
                    'columns': columns,
                    'row_count': len(data),
                    'data': data,
                })
            else:
                print(f"    [!] DS{idx}: niciun rezultat")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  [EROARE] DS{idx} ({name}): {e}")

    # Merge cu dashboard_data.js
    if all_datasets:
        merge_dashboard_data(all_datasets)

    # Sumar
    print(f"\n{'='*60}")
    print(f" SUMAR GA4")
    print(f"{'='*60}")
    total_rows = sum(d['row_count'] for d in all_datasets)
    print(f"  Perioada: {start_date} — {end_date}")
    print(f"  Datasets: {len(all_datasets)}")
    print(f"  Total randuri: {total_rows}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'='*60}")

    # Summary JSON — citit de collect_google_meta_ads_and_GA4.py
    try:
        import json as _json
        summary_path = SCRIPT_DIR / "_pull_summary_ga4.json"
        summary_payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "interval": {"start": start_date, "end": end_date, "days": nr_zile},
            "property_id": GA4_PROPERTY_ID,
            "datasets": [
                {"name": d["name"], "index": d["dataset_index"], "rows": d["row_count"]}
                for d in all_datasets
            ],
            "total_rows": total_rows,
            "output_dir": str(OUTPUT_DIR),
        }
        with open(summary_path, "w", encoding="utf-8") as _f:
            _json.dump(summary_payload, _f, ensure_ascii=False, indent=2)
        print(f"  Summary JSON: {summary_path}")
    except Exception as _e:
        print(f"  [!] Nu am putut scrie summary JSON GA4: {_e}")


if __name__ == '__main__':
    main()
