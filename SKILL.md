---
name: ga4-analytics
description: |
  Skill for extracting analytics data from Google Analytics 4 (GA4) Data API. Use this skill
  whenever the user asks about GA4 metrics, funnels, engagement, sessions, feature usage,
  subscription distribution, or wants to pull data from their GA4 property. Also trigger when
  the user mentions GA4 property ID, analytics.readonly scope, or GA4 Data API.
---

# GA4 Analytics Skill

This skill provides everything needed to connect to the Google Analytics 4 Data API (REST),
extract funnel, engagement, and feature usage data across iOS, Android, and Web platforms,
and export it for dashboards or further analysis.

## Quick Start

1. Ensure `config/ga4.ini` exists (copy from `config/ga4.template.ini`)
2. If no refresh token yet, run `python scripts/get_ga4_refresh_token.py`
3. Pull all datasets: `python scripts/run_GA4.py`

## Prerequisites

```bash
pip install requests
```

## Authentication Setup

GA4 Data API requires:

1. **OAuth Client ID + Secret** — from Google Cloud Console (can reuse the same OAuth app as Google Ads, but needs a SEPARATE refresh token with different scope)
2. **Refresh Token** — with scope `analytics.readonly` (NOT the same as Google Ads scope `adwords`)
3. **Property ID** — numeric GA4 property ID (from Google Analytics > Admin > Property Settings)

All credentials go in `config/ga4.ini` (gitignored). See `config/ga4.template.ini` for the format.

### Important: Separate Refresh Token

GA4 and Google Ads use **different OAuth scopes**:
- Google Ads: `https://www.googleapis.com/auth/adwords`
- GA4: `https://www.googleapis.com/auth/analytics.readonly`

Even if you use the same OAuth app (same client_id/secret), you need **separate refresh tokens**. Do NOT copy the Google Ads refresh_token into ga4.ini.

### Obtaining a Refresh Token

```bash
python scripts/get_ga4_refresh_token.py
```

The script reads `client_id`/`client_secret` from `config/ga4.ini`, opens an OAuth URL, and writes the token back automatically.

**Critical**: Same as Google Ads — if OAuth consent screen is in "Testing" mode, tokens expire after **7 days**. Move to "In production" for permanent tokens.

### Enabling the API

In Google Cloud Console:
1. Go to APIs & Services > Library
2. Search for "Google Analytics Data API"
3. Enable it on the same project as your OAuth credentials

## Available Scripts

### `run_GA4.py` — Primary Data Extraction

Extracts 10 datasets from GA4 covering iOS, Android, and Web platforms.

```bash
python scripts/run_GA4.py                   # all datasets
python scripts/run_GA4.py funnel            # iOS conversion funnel
python scripts/run_GA4.py engagement        # cross-platform sessions & engagement
python scripts/run_GA4.py features          # iOS feature usage + error rates
python scripts/run_GA4.py abonamente        # iOS subscription distribution
python scripts/run_GA4.py funnel_android    # Android conversion funnel
python scripts/run_GA4.py features_android  # Android feature usage
python scripts/run_GA4.py web               # Web conversion funnel
```

**Output**: CSV files in `rezultate/` directory + `dashboard_data.js` for HTML dashboard rendering.

### Datasets Generated

| ID | Name | Platform | Description |
|----|------|----------|-------------|
| DS1 | Funnel iOS | iOS | Daily in-app conversion funnel (steps by event) |
| DS2 | Engagement | Cross-platform | Daily sessions, engagement rate, avg session duration |
| DS3 | Features iOS | iOS | Feature usage counts + error rates |
| DS4 | Subscriptions iOS | iOS | Subscription tier distribution |
| DS5 | KPI Summary iOS | iOS | Single-row summary of key metrics |
| DS6 | Funnel Android | Android | Daily in-app conversion funnel |
| DS7 | Features Android | Android | Feature usage + error rates |
| DS8 | Subscriptions Android | Android | Subscription tier distribution |
| DS9 | KPI Summary Android | Android | Single-row summary |
| DS10 | Funnel Web | Web | Web conversion funnel |

### `get_ga4_refresh_token.py` — OAuth Token Helper

Interactive OAuth flow for GA4 scope. Writes token to `config/ga4.ini`.

**Note on the URL paste step**: When Google redirects to `http://localhost/?code=...&scope=...`, the page won't load (expected). Copy the FULL URL from the browser address bar and paste it into the script prompt. Do NOT run it in CMD where `&` is interpreted as a command separator — use PowerShell or paste carefully.

## Config Loader

All scripts use `config_loader.py` (included in `scripts/`) which provides:

- `load_ga4()` — reads `config/ga4.ini`, validates non-placeholder values
- Placeholder detection for incomplete setup
- Config discovery: `config/` relative to script or project root

## GA4 API Specifics

- **API Version**: `v1beta` (configured in `ga4.ini`)
- **Rate Limits**: 10 concurrent requests, ~10,000 requests/day per property
- **Date Ranges**: Supports custom ranges; default is last 180 days
- **Dimensions & Metrics**: Standard GA4 dimensions (date, platform, eventName) and metrics (sessions, activeUsers, engagementRate)

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| `invalid_grant: Token has been expired or revoked` | Consent screen in Testing mode (7-day expiry) | Move to Production; re-run `get_ga4_refresh_token.py` |
| `invalid_client` | client_secret empty or wrong | Check `config_loader.py` output; re-copy from Cloud Console |
| `403: Google Analytics Data API has not been enabled` | API not activated | Enable in Cloud Console > APIs & Services > Library |
| `Property not found` | Wrong property_id or no access | Verify in GA4 Admin > Property Settings; ensure OAuth user has access |
| `UNAUTHENTICATED` with correct token | Wrong scope (used Ads token instead of Analytics) | Generate NEW token with `get_ga4_refresh_token.py` |

## Credential Security

- `config/ga4.ini` is gitignored — never commit credentials
- `config/ga4.template.ini` is the committed template with `YOUR_*` placeholders
- GA4 and Google Ads tokens are separate — never mix scopes
- If a secret leaks to GitHub, Google auto-revokes it
