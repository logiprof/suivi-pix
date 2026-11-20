"""Tests de base (sans connexion a Pix). Lancer : python3 -m unittest discover -s tests"""
import json
import os
import sys
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["SUIVI_PIX_MOCK"] = "1"
import server  # noqa: E402


class ProfileTests(unittest.TestCase):
    def test_parse_profile(self):
        doc = {
            "data": {"type": "profiles", "id": "1", "attributes": {"pix-score": 42}},
            "included": [
                {"type": "areas", "id": "a1", "attributes": {"title": "Information et données"}},
                {"type": "scorecards", "id": "s2", "attributes": {"index": "1.10", "name": "X", "level": 0, "earned-pix": 0, "status": "NOT_STARTED"}},
                {"type": "scorecards", "id": "s1", "attributes": {"index": "1.2", "name": "Gérer des données", "level": 2,
                                                                  "earned-pix": 17, "status": "STARTED"},
                 "relationships": {"area": {"data": {"type": "areas", "id": "a1"}}}},
            ],
        }
        p = server.parse_profile(doc)
        self.assertEqual(p["pixScore"], 42)
        self.assertEqual([c["index"] for c in p["scorecards"]], ["1.2", "1.10"])
        self.assertEqual(p["scorecards"][0]["level"], 2)
        self.assertEqual(p["scorecards"][0]["area"], "Information et données")

    def test_error_messages(self):
        self.assertEqual(server._error_message(401, '{"errors":[{"title":"Unauthorized"}]}'),
                         ("Identifiant ou mot de passe incorrect.", "credentials"))
        msg, kind = server._error_message(401, '{"errors":[{"code":"SHOULD_CHANGE_PASSWORD"}]}')
        self.assertIn("changer son mot de passe", msg)
        self.assertEqual(kind, "other")


class XlsxTests(unittest.TestCase):
    def test_roundtrip(self):
        data = server.write_xlsx([{"name": "Résultats", "rows": [
            [{"v": "Nom", "s": "header"}, {"v": "Identifiant", "s": "header"}, {"v": "Mot de passe", "s": "header"}],
            ["Dupont Léa", "lea.dupont", 12345],
            ["Martin & Fils <test>", "a@b.ch", {"v": 1.5, "s": "ok"}],
        ]}])
        rows = server.read_xlsx(data)
        self.assertEqual(rows[0], ["Nom", "Identifiant", "Mot de passe"])
        self.assertEqual(rows[1], ["Dupont Léa", "lea.dupont", "12345"])
        self.assertEqual(rows[2][0], "Martin & Fils <test>")

    def test_not_xlsx(self):
        with self.assertRaises(server.PixError):
            server.read_xlsx(b"pas un classeur")


class PdfTests(unittest.TestCase):
    def test_student_pdf_one_page_each(self):
        import pdf_report
        st = {"name": "Dupont Léa", "classe": "9VG2", "login": "lea", "date": "12.11.2026 08:05", "status": "evalue",
              "total": 12, "totalLabel": "12 (4 + 2 + 6)", "counted": 11, "penaltyTotal": 1, "finalPoints": 10, "grade": "5.50",
              "competences": [{"index": "3.1", "name": "Développer des documents textuels", "right": "Niveau 4", "detail": "39 Pix", "comment": ""}] * 3,
              "penalties": [{"label": "Retard", "points": 1}], "remark": "Bravo (et merci) \\ ok"}
        pdf = pdf_report.make_pdfs([st, dict(st, name="Rossi Emma", status="non_remis")], {"title": "Pix", "maxPoints": 11, "rules": ["Règle"]}, "combined")
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Count 2", pdf)
        z = pdf_report.make_pdfs([st, st], {"maxPoints": 11}, "zip")
        import zipfile, io
        names = zipfile.ZipFile(io.BytesIO(z)).namelist()
        self.assertEqual(names, ["9VG2 - Dupont Léa.pdf", "9VG2 - Dupont Léa (2).pdf"])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server._server = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = "http://127.0.0.1:%d" % server._server.server_address[1]
        threading.Thread(target=server._server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        server._server.shutdown()

    def post(self, path, body, token=True):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"X-Suivi-Token": server.SESSION_TOKEN} if token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_page(self):
        with urllib.request.urlopen(self.base + "/") as r:
            html = r.read().decode()
        self.assertIn(server.SESSION_TOKEN, html)
        self.assertIn(server.VERSION, html)

    def test_token_required(self):
        self.assertEqual(self.post("/api/check", {}, token=False)[0], 403)

    def test_check_mock(self):
        code, res = self.post("/api/check", {"domain": "app.pix.fr", "login": "lea", "password": "x"})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["scorecards"]), 16)
        code, res = self.post("/api/check", {"domain": "app.pix.fr", "login": "lea", "password": "faux"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["kind"], "credentials")

    def test_unknown_domain(self):
        _, res = self.post("/api/check", {"domain": "evil.example", "login": "a", "password": "b"})
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
