# Frickelalarm – Konzept einer Home-Assistant-Alarmanlagen-Integration

> Arbeitstitel / Domain: `frickelalarm` (festgelegt). Ziel: eine vollwertige, UI-konfigurierbare
> Alarmanlagen-Integration für Home Assistant, installierbar über HACS bzw. den
> **Home Assistant Marketplace** (seit HA 2026.11 ist HACS als „Marketplace" direkt in HA eingebaut;
> benutzerdefinierte Repositories funktionieren weiterhin).

## 1. Ziel

Eine Integration, mit der man **ohne YAML** eine Alarmanlage einrichtet:
- relevante **Sensoren** (Tür-/Fensterkontakte, Bewegungsmelder …) auswählen,
- festlegen, in welchem **Modus** welche Sensoren scharf sind,
- **Reaktionen** definieren (Sirene, Licht, Benachrichtigung, Skript …),
- mit alarm-typischer **Logik**: Ein-/Ausgangsverzögerung, Voralarm, Auto-Scharf, Sabotage etc.

Die Integration bringt die **komplette Alarm-Engine** selbst mit (nicht nur ein Panel) und steuert den Ablauf.

## 2. Vorbild & Abgrenzung (ehrlich)

Es gibt bereits **Alarmo** (HACS, sehr verbreitet) mit genau diesem Funktionsumfang. Wir bauen bewusst eigen –
Lerneffekt, volle Kontrolle, eigene Akzente. Mögliche **Differenzierung** (müssen wir nicht alles machen):
- schlanker, meinungsstarker Einrichtungs-Assistent (Schritt-für-Schritt im Config-Flow),
- „Aktoren-Übersicht": zeigt dir alle relevanten Aktoren/Sensoren + deren Live-Zustand an einem Ort,
- enge Integration mit dem bestehenden Frickelfabrik-Dashboard-Look,
- klare, deutschsprachige Doku + Beispiele.

## 3. Architektur

**Typ:** Custom Integration (`custom_components/frickelalarm/`), Einrichtung **nur per UI** (Config-Flow + Options-Flow),
keine YAML-Konfiguration. `config_entry` = eine Alarm-Instanz (später ggf. mehrere Bereiche/Partitionen).

### Entitäten
- **`alarm_control_panel.frickelalarm`** – Herzstück. Nutzt die HA-Standardzustände:
  `disarmed`, `arming`, `armed_home`, `armed_away`, `armed_night`, `armed_vacation`, `pending`, `triggered`.
  Unterstützte Features: ARM_HOME/ARM_AWAY/ARM_NIGHT/ARM_VACATION, TRIGGER, (optional) Code.
- **`sensor.frickelalarm_status`** – menschenlesbarer Zustand + Attribute (offene Sensoren, Grund des Alarms, Restzeit Timer).
- Optional: **`binary_sensor`** je „offener Sensor beim Scharfschalten" / Sabotage, **`switch`** „Nachtmodus-Bypass" etc. (später).

### Komponenten (intern)
- **Coordinator / AlarmEngine**: zentrale State-Machine, hält Konfiguration, hört auf Sensor-State-Changes, steuert Timer.
- **Store**: Konfiguration (Modi, Sensoren, Aktionen) in `config_entry.options` (UI-editierbar), ergänzt um einen
  kleinen `helpers.storage.Store` für Laufzeitdaten (letzter Alarm, Logbuch).
- **Actions-Runner**: führt bei Zustandswechseln die konfigurierten Reaktionen aus (service calls).

### State-Machine (Kern)
```
disarmed ──arm_*──▶ arming (Ausgangsverzögerung) ──▶ armed_*
armed_* ──Sensor löst aus──▶ pending (Eingangsverzögerung) ──▶ triggered
armed_* ──Sofort-Sensor (keine Verz.)──────────────────────▶ triggered
triggered ──(Alarmdauer abgelaufen | disarm)──▶ armed_* / disarmed
jeder Zustand ──disarm──▶ disarmed
```
- **Ausgangsverzögerung (exit delay):** Zeit zum Verlassen, bevor wirklich scharf.
- **Eingangsverzögerung (entry delay):** Zeit zum Unscharfschalten, bevor Vollalarm (nur für „verzögerte" Sensoren).
- **Sofort-Sensoren:** lösen ohne Verzögerung aus (z. B. Glasbruch, Rauch).
- **Voralarm (optional):** leiser Hinweis während `pending`.

## 4. Konfigurationsmodell (per UI)

**Config-Flow (Ersteinrichtung):**
1. Name der Anlage, optional Code (PIN) + „Code zum Scharfschalten nötig?".
2. Modi aktivieren (Zuhause / Abwesend / Nacht / Urlaub).

**Options-Flow (jederzeit änderbar, Menü-geführt):**
- **Sensoren**: je Sensor → Typ (Tür/Fenster/Bewegung/Glasbruch/Rauch/Sabotage), pro Modus „scharf ja/nein",
  „verzögert ja/nein" (Eingangsverzögerung), „immer scharf" (auch unscharf, z. B. Rauch).
- **Modi/Zeiten**: Ein-/Ausgangsverzögerung je Modus, Alarmdauer, Auto-Scharf (optional), Wiederschärfen nach Alarm.
- **Aktionen**: pro Ereignis (`arming`, `armed`, `pending`, `triggered`, `disarmed`) eine Liste von Reaktionen:
  - Entitäten schalten (Sirene `switch`/`siren`, Licht `light`),
  - Benachrichtigung (`notify.*` mit Text-Vorlage),
  - beliebiger Service-Call / Skript / Szene.
- **Aktoren-Übersicht**: read-only Ansicht aller gewählten Sensoren/Aktoren + Live-Zustand (Kern-Wunsch).

## 5. Dienste (Services)
- `frickelalarm.arm` / `disarm` / `trigger` (mit `mode`, `code`, `skip_delay`),
- `frickelalarm.bypass` (Sensor temporär ausklammern),
- `frickelalarm.reset`.
Events fürs Logbuch: `frickelalarm_triggered`, `frickelalarm_armed`, … (mit Grund/Quelle).

## 6. HACS / Marketplace-Weg
Damit es in HACS (und ggf. in die HACS-Default-Liste) kann:
- Repo-Struktur: `custom_components/frickelalarm/` mit `manifest.json` (domain, name, version, codeowners, iot_class,
  `config_flow: true`, requirements), `__init__.py`, `config_flow.py`, `alarm_control_panel.py`, `const.py`, `translations/`.
- `hacs.json` im Repo-Root (`name`, `render_readme: true`).
- Aussagekräftige **README** + **Releases mit Tags** (HACS liest Releases).
- **Brands-Eintrag** (Logo/Icon) im `home-assistant/brands`-Repo (nötig fürs offizielle Listing).
- Qualitätskriterien: UI-Config-Flow, Übersetzungen (de/en), `strict typing`, Tests (pytest-homeassistant-custom-component),
  `hassfest`- und `HACS-Action`-CI (GitHub Actions).
- Einreichung: zuerst als **Custom Repository** in HACS nutzbar; später PR an `hacs/default` für die offizielle Liste.

## 7. Entwicklung & Test auf dem Pi
- HA läuft in Docker (`/home/norbert/homeassistant/config`).
- Entwicklung im Repo `~/projekte/frickelalarm`; zum Testen `custom_components/frickelalarm` in die HA-Config
  **symlinken** (oder kopieren) → `docker restart homeassistant` → Integration „hinzufügen".
- Logs: `docker logs homeassistant | grep frickelalarm`.

## 8. Roadmap (Phasen)
- **P1 – Gerüst**: Integration lädt, Config-Flow legt eine Instanz an, `alarm_control_panel` mit arm/disarm (ohne Verzögerung). In HA einrichtbar.
- **P2 – Engine** ✅ (0.2.0): Zustandsmaschine mit Ein-/Ausgangsverzögerung, Sensorauswahl je Modus, Auslösen → `triggered`, Alarmdauer + Wiederschärfen, „immer scharf"-Sensoren.
- **P3 – Aktionen** ✅ (0.3.0): Reaktionen pro Ereignis – Aktoren (Sirene/Licht/Schalter) an bei `triggered`, aus danach; optionale Benachrichtigung (Dienst + Text-Template + Ereignisauswahl).
- **P4 – Komfort**: Aktoren-Übersicht, Bypass, Code/PIN, Sabotage/„immer scharf", Logbuch-Events, Übersetzungen de/en.
- **P5 – Qualität & HACS**: Tests, CI (hassfest + HACS-Action), README, Brands-Eintrag, erstes Release-Tag; als Custom-Repo testbar.
- **P6 – (optional)**: Einreichung HACS-Default, Lovelace-Karte im Frickelfabrik-Look.

## 9. Getroffene Entscheidungen (2026-11-07)
- **Name/Domain**: `frickelalarm` – festgelegt.
- **Mehrere Bereiche/Partitionen**: **ja**, von Anfang an mitdenken. Umsetzung: **1 Config-Entry = 1 Bereich/Panel**
  (mehrere Bereiche = mehrere Einträge der Integration). Das ist HA-idiomatisch und braucht keine Sub-Partition-Logik.
- **Eigene Lovelace-Karte** (Frickelfabrik-Look): **ja** – eigenes Frontend-Modul (Phase P6), Standard-Panel funktioniert davor.
- **PIN/Code**: **konfigurierbar** – pro Bereich optional ein Code; separat einstellbar „Code zum Scharfschalten nötig"
  und „Code zum Unscharfschalten nötig".

Offen (später): neutraler Marktname zusätzlich?, Brand-Logo-Design.
