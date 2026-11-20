"""Fiches PDF par eleve au style LogiExam (bandeau sombre, filet jaune, grille
d'informations, synthese de la note, cartes). Bibliotheque standard uniquement :
le PDF est ecrit a la main, comme dans LogiExam (polices Helvetica standard).
"""
import io
import re
import time
import zipfile

# Couleurs LogiOne / LogiExam
DARK = (49, 58, 69)
YELLOW = (245, 196, 0)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
GREEN = (6, 95, 70)
BLUE = (30, 64, 175)
SLATE = (71, 85, 105)
RED = (180, 35, 24)

# Largeurs des caracteres (WinAnsi 32..255, pour 1000 unites)
_W = {
    "F1": (278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 556, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 556, 611, 556, 556, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 556, 500, 667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500),
    "F2": (278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 761, 556, 556, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 556, 611, 556, 556, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 556, 500, 667, 278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556),
    "F3": (278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 556, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 556, 611, 556, 556, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 556, 500, 667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500),
}

_REPL = {"−": "-", "≤": "<=", "≥": ">=", "✓": "", "✔": "", " ": " ", " ": " ",
         "→": "->", "←": "<-", "▲": "", "▼": ""}


def _plain(text):
    text = str(text if text is not None else "")
    for a, b in _REPL.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def _enc(text):
    return _plain(text).encode("cp1252", "replace")


def text_width(text, size, font="F1"):
    w = _W[font]
    return sum(w[b - 32] if 32 <= b <= 255 else 556 for b in _enc(text)) * size / 1000.0


def wrap(text, width, size, font="F1"):
    """Coupe le texte en lignes de largeur maximale `width` (points)."""
    text = _plain(text)
    if not text:
        return [""]
    lines, cur = [], ""
    for word in text.split(" "):
        cand = (cur + " " + word) if cur else word
        if text_width(cand, size, font) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def _esc(text):
    raw = _enc(text)
    out = bytearray()
    for b in raw:
        if b in (0x5C, 0x28, 0x29):
            out += b"\\" + bytes([b])
        else:
            out.append(b)
    return out.decode("latin-1")


def _color(rgb):
    r, g, b = (max(0, min(255, int(c))) / 255 for c in rgb)
    return "%.3f %.3f %.3f rg %.3f %.3f %.3f RG\n" % (r, g, b, r, g, b)


class Doc:
    def __init__(self, header_title, header_date, header_class="", footer_left="", footer_right=""):
        self.pages, self.content, self.y = [], "", 0
        self.footer_left, self.footer_right = _plain(footer_left), _plain(footer_right)
        self.header_title, self.header_date, self.header_class = header_title, header_date, _plain(header_class)

    # --- primitives
    def text(self, x, y, size, text, font="F1", rgb=(0, 0, 0)):
        self.content += _color(rgb) + "BT /%s %g Tf %.2f %.2f Td (%s) Tj ET\n" % (font, size, x, y, _esc(text))

    def fill(self, x, y, w, h, rgb):
        self.content += _color(rgb) + "%.2f %.2f %.2f %.2f re f\n" % (x, y, w, h)

    def rect(self, x, y, w, h):
        self.content += "0.741 0.792 0.859 RG 0.5 w %.2f %.2f %.2f %.2f re S\n" % (x, y, w, h)

    def poly(self, pts, rgb):
        p = " ".join("%.2f %.2f %s" % (x, y, "m" if i == 0 else "l") for i, (x, y) in enumerate(pts))
        self.content += _color(rgb) + p + " h f\n"

    # --- mise en page
    def _footer(self):
        # Pied de page : formation / branche a gauche, enseignant a droite
        if not (self.footer_left or self.footer_right):
            return
        self.fill(42, 32, 511, 0.6, (210, 214, 205))
        if self.footer_left:
            self.text(42, 20, 8, self.footer_left, "F1", MUTED)
        if self.footer_right:
            self.text(553 - text_width(self.footer_right, 8, "F2"), 20, 8, self.footer_right, "F2", MUTED)

    def new_page(self):
        if self.content:
            self._footer()
            self.pages.append(self.content)
        self.content, self.y = "", 748
        # Bandeau LogiExam : fond sombre, filet jaune, logo a gauche, titre et date a droite
        self.fill(0, 778, 595, 64, DARK)
        self.fill(0, 774, 595, 4, YELLOW)
        self._logo(30, 778)
        if self.header_class:
            # Classe en grand (jaune) pour trier et distribuer les feuilles
            cls = "Classe " + self.header_class
            size = 22 if text_width(cls, 22, "F2") <= 300 else 16
            self.text(553 - text_width(self.header_title, 10, "F2"), 824, 10, self.header_title, "F2", (201, 209, 217))
            self.text(553 - text_width(cls, size, "F2"), 801, size, cls, "F2", YELLOW)
            self.text(553 - text_width(self.header_date, 8), 787, 8, self.header_date, "F1", (201, 209, 217))
        else:
            self.text(553 - text_width(self.header_title, 15, "F2"), 808, 15, self.header_title, "F2", (255, 255, 255))
            self.text(553 - text_width(self.header_date, 9), 792, 9, self.header_date, "F1", (201, 209, 217))

    def _logo(self, x, y0):
        # Cube vert avec coche jaune (comme le logo LogiExam) + « Suivi Pix »
        cx, cy = x + 22, y0 + 30
        s = 15
        top = [(cx, cy + 2 * s * 0.55), (cx + s, cy + s * 0.55), (cx, cy), (cx - s, cy + s * 0.55)]
        left = [(cx - s, cy + s * 0.55), (cx, cy), (cx, cy - s * 1.15), (cx - s, cy - s * 0.6)]
        right = [(cx, cy), (cx + s, cy + s * 0.55), (cx + s, cy - s * 0.6), (cx, cy - s * 1.15)]
        self.poly(top, (47, 174, 95))
        self.poly(left, (16, 84, 38))
        self.poly(right, (21, 128, 52))
        self.content += _color(YELLOW) + "2.2 w 1 J 1 j %.2f %.2f m %.2f %.2f l %.2f %.2f l S 0.5 w 0 J 0 j\n" % (
            cx + 3.5, cy - 6, cx + 7, cy - 10, cx + 12.5, cy - 2.5)
        self.text(x + 48, y0 + 24, 22, "Suivi", "F2", (255, 255, 255))
        self.text(x + 48 + text_width("Suivi", 22, "F2") + 6, y0 + 24, 22, "Pix", "F2", YELLOW)

    def student_banner(self, name):
        """Nom et prenom de l'eleve en grand, sous le bandeau, avec un filet jaune a gauche."""
        size = 22
        lines = wrap(name, 495, size, "F2")
        if len(lines) > 1:
            size = 19
            lines = wrap(name, 495, size, "F2")
        lead = size + 4
        height = 14 + len(lines) * lead
        top = self.y + 4
        self.fill(42, top - height - 2, 4, height + 2, YELLOW)
        self.text(54, top - 9, 8, "ÉLÈVE", "F2", MUTED)
        for i, line in enumerate(lines):
            self.text(54, top - 14 - size + 4 - i * lead, size, line, "F2", DARK)
        self.y = top - height - 10

    def ensure(self, h):
        if self.y - h < 54:
            self.new_page()

    def section(self, title, keep=0):
        lines = wrap(title, 500, 14, "F2")
        if self.y < 740:
            self.y -= 8
        self.ensure(34 + (len(lines) - 1) * 18 + keep)
        for i, line in enumerate(lines):
            self.text(42, self.y - i * 18, 14, line, "F2", DARK)
        self.y -= (len(lines) - 1) * 18
        self.fill(42, self.y - 8, 60, 3, YELLOW)
        self.fill(102, self.y - 7, 451, 1, (210, 214, 205))
        self.y -= 22

    def info_grid(self, rows):
        """Grille d'informations LogiExam ; chaque ligne a son nombre de colonnes."""
        heights = []
        for row in rows:
            colw = 495 / len(row)
            h = 0
            for it in row:
                big = len(it) > 2 and it[2] == "big"
                n = len(wrap(it[1], colw - 14, 12 if big else 9, "F2" if big else "F1"))
                h = max(h, 13 + n * (14 if big else 11) + 2)
            heights.append(h + 8)
        height = 16 + sum(heights)
        self.ensure(height + 10)
        top = self.y
        self.fill(42, top - height, 511, height, (248, 250, 252))
        self.rect(42, top - height, 511, height)
        y_row = top - 20
        for r, row in enumerate(rows):
            colw = 495 / len(row)
            for col, it in enumerate(row):
                x, y = 58 + col * colw, y_row
                big = len(it) > 2 and it[2] == "big"
                self.text(x, y, 8, it[0].upper(), "F2", MUTED)
                for k, line in enumerate(wrap(it[1], colw - 14, 12 if big else 9, "F2" if big else "F1")):
                    self.text(x, y - 14 - k * (14 if big else 11), 12 if big else 9, line, "F2" if big else "F1", GREEN if big else INK)
            y_row -= heights[r]
        self.y -= height + 12

    def score_box(self, items, grade_label, grade):
        height = 106
        self.ensure(height + 12)
        top = self.y
        self.fill(42, top - height, 511, height, (238, 240, 235))
        self.rect(42, top - height, 511, height)
        for row, (label, value) in enumerate(items[:4]):
            y = top - 18 - row * 23.5
            self.text(60, y, 8, label.upper(), "F2", (91, 102, 114))
            self.text(60, y - 12, 11, value, "F2", DARK)
        bx, bw, by, bh = 330, 205, top - height + 12, height - 24
        self.fill(bx, by, bw, bh, DARK)
        self.fill(bx, by + bh - 5, bw, 5, YELLOW)
        self.text(bx + 18, by + bh - 26, 9, grade_label.upper(), "F2", YELLOW)
        size = 22 if len(grade) > 6 else 36
        self.text(bx + 18, by + 14, size, grade, "F2", (255, 255, 255))
        self.y -= height + 12

    def card(self, number, title, right, detail, comment, right_rgb=GREEN, desc=""):
        tl = wrap(title, 380, 11, "F2")
        sl = wrap(desc, 455, 9) if desc else []
        dl = wrap(detail, 455, 10) if detail else []
        cl = wrap(comment, 455, 9.5, "F3") if comment else []
        # positions des lignes (de haut en bas), puis hauteur exacte du cadre
        pos, y = [], -18
        for i, line in enumerate(tl):
            pos.append((82, y, 11, line, "F2", (17, 24, 39))); y -= 14
        y += 1
        for line in sl:
            pos.append((82, y, 9, line, "F1", (51, 65, 85))); y -= 11
        if sl:
            y -= 3
        for line in dl:
            pos.append((82, y, 10, line, "F1", BLUE)); y -= 12.5
        for line in cl:
            pos.append((82, y, 9.5, line, "F3", SLATE)); y -= 12
        height = -y + 1
        self.ensure(height + 8)
        top = self.y
        self.fill(42, top - height, 511, height, (255, 255, 255))
        self.rect(42, top - height, 511, height)
        self.text(58, top - 18, 12, "%s." % number, "F2", (17, 24, 39))
        self.text(535 - text_width(right, 11, "F2"), top - 18, 11, right, "F2", right_rgb)
        for x, yy, size, line, font, rgb in pos:
            self.text(x, top + yy, size, line, font, rgb)
        self.y -= height + 6

    def note_box(self, title, paragraphs, red_first=False):
        lines = []
        for p in paragraphs:
            p = _plain(p)
            if not p:
                continue
            hang = bool(re.match(r"^(\d+\.|-|•)\s", p))
            bold = p.startswith("ATTENTION")
            for k, piece in enumerate(wrap(p, 470 if hang else 480, 10, "F2" if bold else "F1")):
                lines.append((piece, 14 if hang and k > 0 else 0, "F2" if bold else "F1"))
        height = max(40, 30 + len(lines) * 13 + 2)
        self.ensure(height + 8)
        top = self.y
        self.fill(42, top - height, 511, height, (248, 250, 252))
        self.rect(42, top - height, 511, height)
        self.text(58, top - 16, 9, title.upper(), "F2", SLATE)
        y = top - 31
        for piece, indent, font in lines:
            self.text(58 + indent, y, 10, piece, font, RED if font == "F2" else INK)
            y -= 13
        self.y -= height + 10

    def small_note(self, title, paragraphs):
        """Rappel discret en bas de fiche (texte gris 8 pt)."""
        lines = []
        for p in paragraphs:
            lines += wrap(p, 500, 8)
        height = 14 + len(lines) * 10
        if self.y - height - 4 < 38:   # pas la place au-dessus du pied de page : on l'omet
            return
        self.y -= 4
        self.fill(42, self.y + 6, 511, 0.6, (210, 214, 205))
        self.text(42, self.y - 6, 8, title.upper(), "F2", MUTED)
        y = self.y - 18
        for line in lines:
            self.text(42, y, 8, line, "F1", MUTED)
            y -= 10
        self.y -= height + 6

    def alert_box(self, title, text):
        lines = wrap(text, 470, 10)
        height = max(60, 40 + len(lines) * 13 + 8)
        self.ensure(height + 10)
        top = self.y
        self.fill(42, top - height, 511, height, (254, 228, 226))
        self.fill(42, top - height, 8, height, RED)
        self.rect(42, top - height, 511, height)
        self.text(62, top - 22, 13, title.upper(), "F2", RED)
        y = top - 40
        for line in lines:
            self.text(62, y, 10, line, "F1", (122, 39, 26))
            y -= 13
        self.y -= height + 16

    def finish(self):
        if self.content:
            self._footer()
            self.pages.append(self.content)
            self.content = ""
        return self.pages


def build_pdf(pages, title="Suivi Pix"):
    objs = {3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>",
            6: "<< /Title (%s) /Producer (Suivi Pix) >>" % _esc(title)}
    nxt, refs = 7, []
    for content in pages:
        data = content.encode("latin-1")
        objs[nxt] = ("<< /Length %d >>\nstream\n" % len(data)).encode("latin-1") + data + b"endstream"
        objs[nxt + 1] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents %d 0 R >>" % nxt)
        refs.append("%d 0 R" % (nxt + 1))
        nxt += 2
    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(refs), len(refs))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * nxt
    for i in range(1, nxt):
        offsets[i] = len(out)
        body = objs[i] if isinstance(objs[i], bytes) else objs[i].encode("latin-1")
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % nxt
    for i in range(1, nxt):
        out += b"%010d 00000 n \n" % offsets[i]
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF" % (nxt, xref)
    return bytes(out)


def fmt_pts(v):
    try:
        return "%.2f" % float(v)
    except (TypeError, ValueError):
        return str(v)


def student_pages(st, meta):
    """Une fiche eleve sur une page. Tous les calculs viennent de l'interface."""
    doc = Doc("Résultats Pix", meta.get("generatedAt") or time.strftime("%d.%m.%Y %H:%M"), st.get("classe") or "",
              meta.get("footerLeft", ""), meta.get("footerRight", ""))
    doc.new_page()
    max_pts = meta.get("maxPoints", 11)
    doc.student_banner(st.get("name") or "")
    doc.info_grid([[("Cours", meta.get("title") or "Compétences élémentaires en informatique : PIX", "big")],
                   [("Classe", st.get("classe") or "-"), ("Compte Pix", st.get("login") or "-"),
                    ("Accès transmis le", st.get("date") or "-"), ("Niveaux relevés le", st.get("checkedAt") or "-")]])

    if st.get("status") == "non_remis":
        doc.alert_box("Travail non remis - " + (("note : " + st["grade"]) if st.get("grade") else "sans note"),
                      st.get("nonRemisText") or "Les identifiants Pix transmis sont incorrects : le travail est inévaluable et n'est pas considéré comme remis.")

    comps = st.get("competences") or []
    if comps:
        doc.section(meta.get("compsTitle") or "Compétences travaillées en autonomie sur Pix", keep=60)
        for i, c in enumerate(comps, 1):
            doc.card(i, "%s %s" % (c.get("index", ""), c.get("name", "")), c.get("right", ""), c.get("detail", ""), c.get("comment", ""),
                     RED if c.get("alert") else GREEN, c.get("desc", ""))

    doc.section("Synthèse de la note", keep=110)
    doc.score_box([
        ("Total des niveaux retenus", st.get("totalLabel") or fmt_pts(st.get("total", 0))),
        ("Points pris en compte", "%s / %s" % (fmt_pts(st.get("counted", 0)), fmt_pts(max_pts))),
        ("Pénalités (points)", ("-" if float(st.get("penaltyTotal") or 0) else "") + fmt_pts(st.get("penaltyTotal", 0))),
        ("Total des points", "%s / %s" % (fmt_pts(st.get("finalPoints", 0)), fmt_pts(max_pts))),
    ], "Note finale", st.get("grade") or "-")
    pens = st.get("penalties") or []
    doc.note_box("Pénalités", [" · ".join("%s : -%s pt" % (p.get("label", ""), fmt_pts(p.get("points", 0))) for p in pens)] if pens else ["Aucune pénalité."])

    if (st.get("remark") or "").strip():
        doc.note_box("Commentaire de l'enseignant", (st.get("remark") or "").splitlines())
    if meta.get("rules"):
        doc.small_note("Rappel des objectifs", meta["rules"])
    return doc.finish()


def safe_name(s):
    s = re.sub(r"[\\/:*?\"<>|]+", "-", _plain(s)).strip(" .-")
    return s or "eleve"


def make_pdfs(students, meta, mode):
    """mode : 'single' (premier eleve), 'combined' (un PDF, une fiche par page), 'zip' (un PDF par eleve)."""
    if mode == "zip":
        buf = io.BytesIO()
        used = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for st in students:
                base = safe_name(("%s - %s" % (st.get("classe"), st.get("name"))) if st.get("classe") else st.get("name"))
                name, n = base, 2
                while name.lower() in used:
                    name = "%s (%d)" % (base, n); n += 1
                used.add(name.lower())
                z.writestr(name + ".pdf", build_pdf(student_pages(st, meta), "Résultats Pix - " + (st.get("name") or "")))
        return buf.getvalue()
    if mode == "single":
        students = students[:1]
    pages = []
    for st in students:
        pages += student_pages(st, meta)
    return build_pdf(pages, "Résultats Pix")
