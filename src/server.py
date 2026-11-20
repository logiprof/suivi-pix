#!/usr/bin/env python3
"""Suivi Pix - serveur local.

Tourne uniquement sur cet ordinateur (127.0.0.1). Il se connecte a Pix avec
les identifiants fournis par l'interface, lit le profil (niveaux par
competence) et renvoie le resultat. Les mots de passe ne sont jamais ecrits
sur le disque.
"""
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.7.0"
# Dans l'app construite (PyInstaller), les fichiers sont dans sys._MEIPASS
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # pdf_report.py a cote du serveur
if sys.platform == "darwin":
    SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/Suivi Pix")
else:
    SUPPORT_DIR = os.path.expanduser("~/.suivi-pix")
SETTINGS_FILE = os.path.join(SUPPORT_DIR, "reglages.json")
if sys.platform == "darwin":
    LOG_FILE = os.path.expanduser("~/Library/Logs/Suivi Pix.log")
else:
    LOG_FILE = os.path.join(SUPPORT_DIR, "suivi-pix.log")


def log(msg):
    """Journal de diagnostic (jamais d'identifiant ni de mot de passe)."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 2_000_000:
            os.replace(LOG_FILE, LOG_FILE + ".old")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass

SESSION_TOKEN = secrets.token_urlsafe(24)
ALLOWED_DOMAINS = ("app.pix.fr", "app.pix.org")
USER_AGENT = "SuiviPix/1.0 (macOS; suivi enseignant)"
MOCK = os.environ.get("SUIVI_PIX_MOCK") == "1"
HEARTBEAT_TIMEOUT = 3 * 3600  # secondes sans aucune activite de la page -> arret

_last_ping = time.time()
_bye_at = None  # la page a ete fermee : arret prevu sauf si elle revient
_server = None


# --------------------------------------------------------------------------
# HTTP vers Pix (urllib, avec repli sur curl si les certificats posent souci)
# --------------------------------------------------------------------------
class PixError(Exception):
    """kind = "credentials" (identifiant / mot de passe a corriger par l'eleve) ou "other" (technique)."""
    def __init__(self, msg, kind="other"):
        super().__init__(msg)
        self.kind = kind


def _http_urllib(method, url, headers, body):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _curl_quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _http_curl(method, url, headers, body):
    # La configuration passe par l'entree standard : rien de sensible
    # n'apparait dans la liste des processus.
    lines = [
        "silent", "show-error",
        "max-time = 20",
        "request = " + _curl_quote(method),
        "url = " + _curl_quote(url),
        'write-out = "\\n%{http_code}"',
    ]
    for k, v in headers.items():
        lines.append("header = " + _curl_quote("%s: %s" % (k, v)))
    if body is not None:
        lines.append("data-binary = " + _curl_quote(body.decode("utf-8")))
    proc = subprocess.run(["curl", "-K", "-"], input="\n".join(lines).encode("utf-8"),
                          capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise PixError("Connexion impossible : " + proc.stderr.decode("utf-8", "replace").strip())
    out = proc.stdout.decode("utf-8", "replace")
    text, _, code = out.rpartition("\n")
    return int(code or 0), text


def http_request(method, url, headers, body=None):
    headers = dict(headers)
    headers.setdefault("User-Agent", USER_AGENT)
    headers.setdefault("Accept-Language", "fr-FR,fr;q=0.9")
    try:
        return _http_urllib(method, url, headers, body)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError) and shutil.which("curl"):
            log("certificats Python indisponibles, passage par curl (%s)" % e.reason)
            return _http_curl(method, url, headers, body)
        raise PixError("Connexion impossible à Pix (%s). Vérifiez la connexion Internet." % e.reason)
    except ssl.SSLError as e:
        if shutil.which("curl"):
            log("erreur SSL, passage par curl (%s)" % e)
            return _http_curl(method, url, headers, body)
        raise
    except (TimeoutError, OSError) as e:
        raise PixError("Pix ne répond pas (%s). Réessayer plus tard." % e)


def _error_message(status, text):
    try:
        data = json.loads(text)
        err = (data.get("errors") or [{}])[0]
        code = err.get("code") or ""
        detail = err.get("detail") or err.get("title") or ""
    except Exception:
        code, detail = "", ""
    known = {
        "SHOULD_CHANGE_PASSWORD": "L'élève doit d'abord changer son mot de passe sur Pix.",
        "USER_IS_TEMPORARY_BLOCKED": "Compte bloqué temporairement après trop d'essais. Réessayer plus tard.",
        "USER_IS_BLOCKED": "Compte bloqué par Pix après trop d'essais.",
    }
    if code in known:
        return known[code], "other"
    if status in (400, 401):
        return "Identifiant ou mot de passe incorrect.", "credentials"
    if status == 429:
        return "Trop de requêtes : Pix demande de patienter.", "other"
    if detail:
        return "Pix a répondu : %s" % detail, "other"
    return "Erreur Pix (code HTTP %s)." % status, "other"


def pix_check(domain, login, password):
    if domain not in ALLOWED_DOMAINS:
        raise PixError("Plateforme inconnue.")
    if MOCK:
        return _mock_profile(login, password)
    base = "https://" + domain + "/api"

    body = urllib.parse.urlencode({
        "grant_type": "password", "username": login, "password": password,
    }).encode("utf-8")
    status, text = http_request("POST", base + "/token", {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }, body)
    if status != 200:
        raise PixError(*_error_message(status, text))
    tok = json.loads(text)
    access, user_id, refresh = tok.get("access_token"), tok.get("user_id"), tok.get("refresh_token")
    if not access or not user_id:
        raise PixError("Réponse de connexion inattendue de Pix.")

    try:
        status, text = http_request("GET", "%s/users/%s/profile" % (base, user_id), {
            "Authorization": "Bearer " + access,
            "Accept": "application/vnd.api+json",
        })
        if status != 200:
            raise PixError(*_error_message(status, text))
        return parse_profile(json.loads(text))
    finally:
        if refresh:  # on referme la session ouverte, en arriere-plan (ne retarde pas la reponse)
            def _revoke():
                try:
                    http_request("POST", base + "/revoke", {
                        "Content-Type": "application/x-www-form-urlencoded",
                    }, urllib.parse.urlencode({"token": refresh, "token_type_hint": "refresh_token"}).encode())
                except Exception:
                    pass
            threading.Thread(target=_revoke, daemon=True).start()


def parse_profile(doc):
    data = doc.get("data") or {}
    attrs = data.get("attributes") or {}
    included = doc.get("included") or []
    areas = {}
    for item in included:
        if item.get("type") == "areas":
            areas[item.get("id")] = item.get("attributes") or {}
    cards = []
    for item in included:
        if item.get("type") != "scorecards":
            continue
        a = item.get("attributes") or {}
        area_id = (((item.get("relationships") or {}).get("area") or {}).get("data") or {}).get("id")
        area = areas.get(area_id) or a.get("area") or {}
        cards.append({
            "index": a.get("index"),
            "name": a.get("name"),
            "level": a.get("level") or 0,
            "earnedPix": a.get("earned-pix") or 0,
            "status": a.get("status"),
            "percentNext": a.get("percentage-ahead-of-next-level"),
            "remainingPix": a.get("remaining-pix-to-next-level"),
            "area": area.get("title"),
        })
    cards.sort(key=lambda c: [int(x) if x.isdigit() else 0 for x in str(c["index"]).split(".")])
    return {"pixScore": attrs.get("pix-score") or 0, "scorecards": cards}


def _mock_profile(login, password):
    import random
    time.sleep(0.4)
    if password == "faux":
        raise PixError("Identifiant ou mot de passe incorrect.", "credentials")
    rnd = random.Random(login)
    idx = ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4",
           "4.1", "4.2", "4.3", "5.1", "5.2"]
    cards = []
    for i in idx:
        lvl = rnd.choice([0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7])
        st = "NOT_STARTED" if lvl == 0 and rnd.random() < .6 else "STARTED"
        cards.append({"index": i, "name": None, "level": lvl, "earnedPix": lvl * 8 + rnd.randint(0, 7),
                      "status": st, "percentNext": rnd.randint(0, 99), "remainingPix": rnd.randint(1, 8), "area": ""})
    return {"pixScore": sum(c["earnedPix"] for c in cards), "scorecards": cards}


# --------------------------------------------------------------------------
# Excel (.xlsx) : lecture (export Microsoft Forms) et ecriture (resultats)
# --------------------------------------------------------------------------
import base64
import io
import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _fmt_number(v):
    try:
        f = float(v)
    except ValueError:
        return v
    if f.is_integer() and "e" not in v.lower():
        return str(int(f))
    return v


def read_xlsx(data):
    """Renvoie les lignes de la premiere feuille (liste de listes de textes)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PixError("Ce fichier n'est pas un classeur Excel .xlsx valide.")
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    # premiere feuille dans l'ordre du classeur
    sheet_path = "xl/worksheets/sheet1.xml"
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        first = wb.find("m:sheets/m:sheet", NS)
        rid = first.get("{%s}id" % NS["r"])
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.findall("pr:Relationship", NS):
            if rel.get("Id") == rid:
                target = rel.get("Target").lstrip("/")
                sheet_path = target if target.startswith("xl/") else "xl/" + target
    except Exception:
        pass
    if sheet_path not in names:
        raise PixError("Impossible de trouver la première feuille du classeur.")
    root = ET.fromstring(z.read(sheet_path))
    rows = []
    for row in root.iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif t == "b" and v is not None:
                val = "VRAI" if v.text == "1" else "FAUX"
            elif v is not None and v.text is not None:
                val = v.text if t in ("str", "e") else _fmt_number(v.text)
            else:
                val = ""
            cells[_col_index(c.get("r"))] = val
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><sz val="11"/><color rgb="FFC0392B"/><name val="Calibri"/></font></fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDF2E4"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFCEBCB"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDECE8"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
STYLE_IDS = {"": 0, "header": 1, "ok": 2, "mid": 3, "bold": 4, "err": 5}


def _col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean_sheet_name(name, used):
    name = re.sub(r"[\[\]:*?/\\]", " ", name or "Feuille")[:31] or "Feuille"
    base, n = name, 2
    while name.lower() in used:
        name = (base[:28] + " " + str(n)); n += 1
    used.add(name.lower())
    return name


def write_xlsx(sheets):
    """sheets = [{name, rows: [[{v, s}|valeur]], widths: [..], freeze: bool}]"""
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>',
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        wb_sheets, wb_rels = [], []
        for i, sh in enumerate(sheets, 1):
            ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
            wb_sheets.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (xml_escape(_clean_sheet_name(sh.get("name"), used), {'"': "&quot;"}), i, i))
            wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i))
            out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                   '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
            if sh.get("freeze"):
                out.append('<sheetViews><sheetView workbookViewId="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>')
            widths = sh.get("widths") or []
            if widths:
                out.append("<cols>" + "".join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (j + 1, j + 1, w) for j, w in enumerate(widths)) + "</cols>")
            out.append("<sheetData>")
            for r, row in enumerate(sh.get("rows") or [], 1):
                cells = []
                for c, cell in enumerate(row):
                    if not isinstance(cell, dict):
                        cell = {"v": cell}
                    v, s = cell.get("v"), STYLE_IDS.get(cell.get("s") or "", 0)
                    ref = "%s%d" % (_col_letter(c), r)
                    sattr = ' s="%d"' % s if s else ""
                    if v is None or v == "":
                        if s:
                            cells.append('<c r="%s"%s/>' % (ref, sattr))
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        cells.append('<c r="%s"%s><v>%s</v></c>' % (ref, sattr, repr(v) if isinstance(v, float) else v))
                    else:
                        cells.append('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, sattr, xml_escape(str(v))))
                out.append('<row r="%d">%s</row>' % (r, "".join(cells)))
            out.append("</sheetData></worksheet>")
            z.writestr("xl/worksheets/sheet%d.xml" % i, "".join(out))
        ct.append("</Types>")
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets></workbook>' % "".join(wb_sheets))
        n = len(sheets)
        wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1))
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>' % "".join(wb_rels))
        z.writestr("xl/styles.xml", _STYLES)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Reglages (jamais de mot de passe)
# --------------------------------------------------------------------------
def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    last = data.get("lastResults") or {}
    for r in (last.get("rows") or []) + (last.get("failures") or []):
        r.pop("password", None)
    os.makedirs(SUPPORT_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_FILE)


# --------------------------------------------------------------------------
# Serveur local
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SuiviPix"

    def log_message(self, fmt, *args):
        pass  # rien dans les journaux (pas d'identifiants)

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        if self.path.split("?")[0] in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
                html = f.read().replace("__SESSION_TOKEN__", SESSION_TOKEN).replace("__VERSION__", VERSION)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        global _last_ping, _bye_at
        if self._host_ok() and self.path == "/api/bye?t=" + SESSION_TOKEN:
            _bye_at = time.time()
            return self._send(200, {"ok": True})
        if not self._host_ok() or self.headers.get("X-Suivi-Token") != SESSION_TOKEN:
            return self._send(403, {"error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": "json"})
        _last_ping = time.time()
        _bye_at = None
        path = self.path
        if path == "/api/ping":
            return self._send(200, {"ok": True})
        if path == "/api/settings/load":
            return self._send(200, load_settings())
        if path == "/api/settings/save":
            save_settings(data)
            return self._send(200, {"ok": True})
        if path == "/api/check":
            t0 = time.time()
            try:
                res = pix_check(data.get("domain", ""), (data.get("login") or "").strip(), data.get("password") or "")
                log("verification ok (%.1f s)" % (time.time() - t0))
                return self._send(200, {"ok": True, **res})
            except PixError as e:
                log("verification refusee (%.1f s) : %s" % (time.time() - t0, e))
                return self._send(200, {"ok": False, "error": str(e), "kind": e.kind})
            except Exception as e:  # erreur imprevue
                import traceback
                log("ERREUR inattendue :\n" + traceback.format_exc())
                return self._send(200, {"ok": False, "error": "Erreur inattendue : %s" % e})
        if path == "/api/xlsx/read":
            try:
                rows = read_xlsx(base64.b64decode(data.get("b64") or ""))
                return self._send(200, {"ok": True, "rows": rows})
            except PixError as e:
                return self._send(200, {"ok": False, "error": str(e)})
            except Exception as e:
                return self._send(200, {"ok": False, "error": "Lecture du fichier Excel impossible (%s)." % e})
        if path == "/api/xlsx/write":
            content = write_xlsx(data.get("sheets") or [])
            return self._send(200, {"ok": True, "b64": base64.b64encode(content).decode("ascii")})
        if path == "/api/log":
            log("page : " + str(data.get("msg", ""))[:500])
            return self._send(200, {"ok": True})
        if path == "/api/pdf":
            import pdf_report
            try:
                data_pdf = pdf_report.make_pdfs(data.get("students") or [], data.get("meta") or {}, data.get("mode") or "combined")
                return self._send(200, {"ok": True, "b64": base64.b64encode(data_pdf).decode("ascii")})
            except Exception:
                import traceback
                log("ERREUR PDF :\n" + traceback.format_exc())
                return self._send(200, {"ok": False, "error": "La création du PDF a échoué."})
        if path == "/api/quit":
            log("arret : bouton Quitter")
            self._send(200, {"ok": True})
            threading.Thread(target=_server.shutdown, daemon=True).start()
            return
        return self._send(404, {"error": "not found"})


def _watchdog():
    # Arret si la page est fermee (signal "bye" sans aucune requete dans les 30 s)
    # ou si plus aucun signe de vie depuis HEARTBEAT_TIMEOUT.
    while True:
        time.sleep(2)
        now = time.time()
        if (_bye_at and now - _bye_at > 30) or now - _last_ping > HEARTBEAT_TIMEOUT:
            log("arret : %s" % ("page fermee" if _bye_at else "inactivite"))
            _server.shutdown()
            return


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Pas de console dans l'app : on journalise au lieu d'ecrire sur stderr
        import traceback
        log("ERREUR serveur :\n" + traceback.format_exc())


def main():
    global _server
    port = int(os.environ.get("SUIVI_PIX_PORT", "0"))
    _server = QuietServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % _server.server_address[1]
    try:
        print(url, flush=True)
    except Exception:  # pas de console dans l'app construite
        pass
    threading.Thread(target=_watchdog, daemon=True).start()
    if os.environ.get("SUIVI_PIX_NO_BROWSER") != "1":
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    log("demarrage v%s (%s, Python %s)" % (VERSION, sys.platform, sys.version.split()[0]))
    try:
        _server.serve_forever()
    except BaseException:
        import traceback
        log("ARRET BRUTAL :\n" + traceback.format_exc())
        raise
    log("arret normal")


if __name__ == "__main__":
    main()
