# Frickelalarm

Eine per UI konfigurierbare **Alarmanlagen-Integration für Home Assistant** – mit eigener
Alarm-Engine (Modi, Ein-/Ausgangsverzögerung, echtes Auslösen) und Mehrbereich-Unterstützung.
Installierbar über HACS bzw. den **Home Assistant Marketplace**.

> **Status: 0.5.0 – öffentliche Beta.** Die Engine läuft inklusive **Reaktionen** und **Komfort**:
> Sensoren je Modus, Verzögerungen, Alarm auslösen, Sirene/Licht schalten, benachrichtigen,
> Sensoren per Dienst ausklammern (Bypass) und Logbuch-Events. Dazu eine automatisierte
> Test-Suite, CI (hassfest + HACS + pytest) und ein eigenes Icon. Siehe [CONCEPT.md](CONCEPT.md).
> Rückmeldungen und Tester sind ausdrücklich willkommen.

## Was schon funktioniert (0.5.0)

- Bedienfeld (`alarm_control_panel`) mit den Modi **Zuhause / Abwesend / Nacht / Urlaub**
- **Sensorauswahl je Modus**: pro Sensor festlegen, in welchen Modi er scharf ist
- **Ausgangsverzögerung** (Zeit zum Verlassen) → Zustand `arming`
- **Eingangsverzögerung** (Zeit zum Unscharfschalten) für „verzögerte" Sensoren → Zustand `pending`
- **Sofort-Sensoren** lösen ohne Verzögerung aus (z. B. Glasbruch)
- **„Immer scharf"**-Sensoren lösen in jedem Zustand aus – auch unscharf (z. B. Rauch/Sabotage)
- **Alarmdauer**, danach automatisches Wiederschärfen in den vorherigen Modus
- **Reaktionen im Alarmfall**: gewählte Aktoren (Sirene/Licht/Schalter) gehen bei `triggered` an
  und danach wieder aus; optionale **Benachrichtigung** je Ereignis mit frei formulierbarem Text
- optionaler **Code/PIN**, getrennt für Scharf- und/oder Unscharfschalten
- **Mehrere Bereiche/Partitionen**: ein Eintrag = ein Bereich
- **Bypass**: Sensoren per Dienst (`frickelalarm.bypass` / `clear_bypass`) temporär ausklammern
  (gilt bis zum nächsten Unscharfschalten; „immer scharf"-Sensoren sind davon ausgenommen)
- **Logbuch-Events** für Automationen: `frickelalarm_armed/arming/pending/triggered/disarmed`
  (mit Bereich, Modus, Auslöser)
- **Sensor- und Aktoren-Übersicht** als Attribute (Live-Zustand, Modi, umgangene Sensoren an einem Ort)
- Zustand übersteht Neustarts

## Qualität

- **Tests**: pytest-Suite (pytest-homeassistant-custom-component) für Config-Flow und Engine
- **CI**: GitHub Actions mit `hassfest`, HACS-Validierung und `pytest`
- **Icon/Logo** im `brand/`-Ordner (Frickelfabrik-Look)

## Was noch kommt

- Eintrag im `home-assistant/brands`-Repo, damit das Icon auch in der HA-Oberfläche
  erscheint, und Aufnahme in die Marketplace-Default-Liste
- eigene Lovelace-Karte im Frickelfabrik-Look (später)

## Installation über HACS / Marketplace (Custom Repository)

> Seit Home Assistant **2026.11** ist HACS als **Marketplace** direkt in HA eingebaut
> (Einstellungen → Marketplace). Benutzerdefinierte Repositories funktionieren weiterhin.

1. **Marketplace** öffnen → oben rechts das Menü (⋮) → **Benutzerdefinierte Repositories**.
2. Repository `https://github.com/ankaios76/frickelalarm`, Kategorie **Integration**, hinzufügen.
3. „Frickelalarm" suchen, herunterladen, **Home Assistant neu starten**.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Frickelalarm"**.

## Manuelle Installation

Ordner `custom_components/frickelalarm` in die Home-Assistant-Config kopieren, HA neu starten,
dann wie oben die Integration hinzufügen.

## Einrichten

1. Beim Hinzufügen: **Name** des Bereichs, optional **Code/PIN**.
2. Danach **Konfigurieren** (Zahnrad) öffnen – menügeführt:
   - **Sensoren**: Tür-/Fensterkontakte, Bewegungsmelder … auswählen. Pro Sensor: in welchen
     Modi scharf, „verzögert" (nutzt die Eingangsverzögerung), „immer scharf".
   - **Verzögerungen & Alarmdauer**: Ausgangs-/Eingangsverzögerung und Alarmdauer in Sekunden.
   - **Reaktionen**: Aktoren (Sirene/Licht/Schalter), die bei Alarm an- und danach ausgehen,
     sowie optional ein Benachrichtigungsdienst, Nachrichtentext und die Ereignisse dafür.
   - **Allgemein**: Code/PIN ändern.

## Voraussetzungen

Home Assistant **2026.2** oder neuer.

## Mitmachen

Das ist ein Hobby-/Lernprojekt der [Frickelfabrik](https://frickelfabrik.de). Ideen, Bug-Reports
und Tester sind willkommen – am besten über die
[Issues](https://github.com/ankaios76/frickelalarm/issues).
Es gibt mit **[Alarmo](https://github.com/nielsfaber/alarmo)** bereits eine ausgereifte,
sehr verbreitete Lösung mit ähnlichem Funktionsumfang – Frickelalarm entsteht bewusst eigen
(Lerneffekt, volle Kontrolle, eigene Akzente).

## Entwicklung

Repo: `~/projekte/frickelalarm`. Zum Testen `custom_components/frickelalarm` in die HA-Config
(`/home/norbert/homeassistant/config/custom_components/`) kopieren und
`docker restart homeassistant`. Logs: `docker logs homeassistant | grep -i frickelalarm`.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
