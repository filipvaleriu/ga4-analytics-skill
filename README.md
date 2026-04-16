# ga4-analytics-skill

Skill Cowork pentru extragere analytics din Google Analytics 4 Data API: funnels conversie (iOS, Android, Web), engagement, feature usage, distributie abonamente.

## Structura

```
ga4-analytics-skill/
├── SKILL.md                                    # Instructiuni principale
├── README.md                                   # Acest fisier
├── .gitignore
├── config/
│   └── ga4.template.ini                        # Template config (placeholdere)
└── scripts/
    ├── config_loader.py                        # Loader centralizat configurari
    ├── run_GA4.py                              # Extragere 10 datasets GA4
    └── get_ga4_refresh_token.py                # Helper OAuth refresh token
```

## Prerequisite

```bash
pip install requests
```

## Setup rapid

1. `cp config/ga4.template.ini config/ga4.ini`
2. Completeaza client_id, client_secret, property_id
3. `python scripts/get_ga4_refresh_token.py` (prima data)
4. `python scripts/run_GA4.py`

## Changelog

- 2026-04-16: Creat ca repo separat din proiectul principal de marketing
