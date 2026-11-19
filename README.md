# Suivi Pix

Petite app Mac pour enseignant·e : à partir de l'export Excel d'un Microsoft Forms (nom, identifiant Pix, mot de passe), elle se connecte au compte Pix de chaque élève et affiche un tableau des niveaux dans les compétences choisies, avec le total des niveaux, la liste des connexions impossibles et un export Excel.

![icône](assets/icon.png)

## Télécharger

- **Version officielle** : onglet [Releases](../../releases) → `Suivi-Pix-macOS.zip`
- **Dernière construction** : onglet [Actions](../../actions) → dernier passage vert de « App Mac » → *Artifacts* → `Suivi-Pix-macOS`

L'app fonctionne sur Mac Intel et Apple Silicon (macOS 11 ou plus récent) et n'a besoin de rien d'autre.

**Premier lancement** : l'app n'est pas signée par un compte développeur Apple, macOS la bloque donc la première fois. Double-cliquer une fois, puis *Réglages Système → Confidentialité et sécurité → Ouvrir quand même*.

## Utilisation

1. L'app s'ouvre dans le navigateur (adresse `127.0.0.1`, elle tourne uniquement sur le Mac).
2. Déposer l'export Excel de Forms (ou un CSV `nom;identifiant;mot de passe`). Les colonnes sont repérées automatiquement et peuvent être corrigées.
3. **Vérifier les niveaux…** → cocher les compétences à observer (niveau visé facultatif) → lancer.
4. Résultats : niveau et Pix par compétence, **total des niveaux**, moyennes, liste séparée des **connexions impossibles**, **export Excel** (3 onglets).

Fermer l'onglet (ou cliquer sur *Quitter*) arrête l'app.

## Confidentialité

- Les mots de passe restent en mémoire pendant l'utilisation et ne sont **jamais écrits sur le disque** ni envoyés ailleurs qu'à Pix.
- Seuls les réglages (compétences, niveaux visés, choix des colonnes) et le dernier tableau de niveaux sont gardés dans `~/Library/Application Support/Suivi Pix/`.
- Le serveur local n'écoute que sur `127.0.0.1` et exige un jeton de session.
- Les fichiers `.csv` / `.xlsx` sont ignorés par Git : ne jamais mettre de fichier d'élèves dans ce dépôt.

## Fonctionnement technique

- `src/server.py` : serveur local (Python, bibliothèque standard uniquement). Connexion via l'API de l'application Pix (`POST /api/token`, puis `GET /api/users/{id}/profile`), comme le fait le site [app.pix.fr](https://app.pix.fr) (code source de Pix : [1024pix/pix](https://github.com/1024pix/pix)). Lecture et écriture des `.xlsx` sans dépendance.
- `src/index.html` : l'interface.
- `suivi_pix.spec` : construction de l'app avec PyInstaller.
- `.github/workflows/build-macos.yml` : construction automatique sur un Mac de GitHub, tests, puis publication.

### Développer

```bash
python3 src/server.py                                   # lance l'app (ouvre le navigateur)
SUIVI_PIX_MOCK=1 python3 src/server.py                  # mode test : faux niveaux, sans Pix
python3 -m unittest discover -s tests -v                # tests
```

### Publier une version

Changer `VERSION` dans `src/server.py`, puis créer un tag :

```bash
git tag v1.2.0 && git push origin v1.2.0
```

GitHub construit l'app et crée la Release avec le `.zip`.
