# Monter un projet

Chaque commande de cette page a été lancée, dans cet ordre, sur une machine
qui n'avait que git et un compilateur C. Là où le guide explique, cette page
dit seulement quoi taper et ce que vous devez voir. Quand quelque chose ne se
passe pas comme c'est écrit ici, c'est un bug de cette page.

*The same steps in English: [`start.md`](start.md).*

---

## 1. Ce qu'il vous faut

| | pour | vérifier avec |
|---|---|---|
| **git** | récupérer Keal, kealeb et vos dépendances | `git --version` |
| **un compilateur C** | `keal build` émet du C et le confie à `cc`, ou à `gcc` ou `clang` quand il n'y a pas de `cc`. `CC=clang` choisit. | `cc --version` |
| **Rust, avec cargo** | construire le compilateur Keal, une fois | `cargo --version` |
| **la bibliothèque SQLite** | seulement si votre programme ouvre une base — `libsqlite3-dev` sur Debian et Ubuntu, `sqlite-devel` sur Fedora, `sqlite` par Homebrew | `pkg-config --libs sqlite3` |
| **node** | seulement pour lancer le test navigateur de kealeb lui-même ; un projet n'en a jamais besoin | |

Linux, macOS et les BSD. Windows n'y est pas encore, et le script de
construction le dit plutôt que d'essayer.

## 2. Keal, le compilateur

kealeb est écrit en Keal, et `keal build` est ce qui fait d'un fichier `.keal`
un exécutable. Construisez-le une fois :

```sh
git clone https://github.com/geneacta/keal
cd keal
cargo build --release
```

Le compilateur est alors dans `target/release/keal`. Mettez-le sur votre
chemin :

```sh
cargo install --path .            # ou : export PATH=$PWD/target/release:$PATH
keal --version                    # keal 1.3.0
```

kealeb déclare le Keal contre lequel il est construit dans son propre
`keal.toml`, et le badge en tête du README le montre. Plus récent convient ;
plus ancien peut refuser quelque chose dont ce cadriciel dépend, et dit quoi.

Le script de construction trouve aussi un compilateur qui n'est **pas** sur
votre chemin : il essaie `$KEAL` d'abord, puis un dépôt `keal` à côté du
projet, puis le chemin. Deux `git clone` côte à côte marchent donc sans
toucher au chemin.

## 3. Deux façons de démarrer

La première vous montre le cadriciel en une minute. La seconde est celle que
vous gardez.

### A. Dans le dépôt de kealeb lui-même

```sh
git clone https://github.com/geneacta/kealeb
cd kealeb
tools/build.sh examples/hello.keal
build/hello
```

Ouvrez `http://127.0.0.1:8080`. C'est une page, mise en forme, en mode sombre
si votre machine l'est, sans aucun JavaScript dessus. Ctrl-C l'arrête.

Les autres [exemples](../examples) sont aussi des programmes entiers, chacun
construit et lancé par la suite de tests :

| | | construire avec |
|---|---|---|
| `hello` | une page | `tools/build.sh examples/hello.keal` |
| `counter` | une page vivante : l'état est sur le serveur, seule la différence traverse | `tools/build.sh examples/counter.keal` |
| `todo` | une liste à compléter, cocher et filtrer — ce à quoi sert une page vivante | `tools/build.sh examples/todo.keal` |
| `files` | servir un répertoire, y compris un fichier plus gros que la machine | `tools/build.sh examples/files.keal` |
| `notes` | une page vivante dont l'état est une base de données | `tools/build.sh examples/notes.keal -lsqlite3` |
| `signin` | mots de passe, sessions, une garde et le jeton CSRF | `tools/build.sh examples/signin.keal -lsqlite3` |

L'exécutable arrive toujours dans `build/`, au nom du fichier.

### B. Votre propre projet

Un projet qui veut kealeb le dit dans un manifeste, et cesse de se soucier
d'où vit le cadriciel.

```sh
mkdir monsite && cd monsite
```

```toml
# keal.toml
[package]
name = "monsite"
version = "0.1.0"

[dependencies]
kealeb = { git = "https://github.com/geneacta/kealeb", tag = "v0.1.0" }
```

```sh
keal fetch
```

```
cloned kealeb (tag v0.1.0)
1 dependency in /home/vous/monsite/.keal/deps
```

Deux choses sont apparues. `.keal/deps/kealeb/` est le cadriciel, extrait à
l'étiquette que vous avez nommée. `keal.lock` note le commit auquel cette
étiquette a résolu, pour qu'une étiquette déplacée en amont ne change pas en
silence ce contre quoi vous construisez — commitez ce fichier. `.keal/deps/`
est votre décision : commitez-le et le projet se construit sans réseau et sans
git, ou ignorez-le et lancez `keal fetch` après chaque extraction. Un
`rev = "…"` nommant un commit marche à la place de `tag`, et `keal fetch` ne
touche à rien d'autre — pas de registre, pas de résolveur, pas de version plus
récente choisie à votre place.

Maintenant le programme :

```keal
// app.keal
import "dep:kealeb/kealeb.keal"

val site = app("Mon site")

site.page("/", { req -> column([
    h1("Bonjour"),
    p("depuis Keal")
])})

site.run(8080)
```

L'import dit `dep:` et le nom de la dépendance, et lit
`.keal/deps/kealeb/kealeb.keal` à côté du `keal.toml` le plus proche.
Construisez-le avec le script venu avec la dépendance :

```sh
.keal/deps/kealeb/tools/build.sh app.keal
build/app
```

La sortie arrive dans **votre** `build/`, pas dans celui de la dépendance. Si
vous préférez voir le seul drapeau que le script ajoute — la surface C de
kealeb est un en-tête, et il faut dire au compilateur où il est :

```sh
mkdir -p build && cd build
keal build ../app.keal -I../.keal/deps/kealeb/runtime
```

`keal build` écrit l'exécutable, et le C qu'il a généré, dans le répertoire
où il tourne, d'où le passage par `build/`. Ajoutez `-lsqlite3` à l'une ou
l'autre commande quand le programme importe `dep:kealeb/src/sql.keal`, et
rien sinon : kealeb ne se lie à aucune bibliothèque tant que vous ne demandez
pas la base de données.

## 4. Le vérifier sans navigateur

Le programme répond à deux questions sur la ligne de commande et sort, au lieu
d'ouvrir un port :

```sh
build/app --routes
```

```
GET /
GET /kealeb/kealeb.css
GET /kealeb/kealeb.js
GET /kealeb/live
```

Les trois dernières sont celles du cadriciel — sa feuille de style, son client
navigateur, et la socket qu'une page vivante ouvre. Et :

```sh
build/app --render /
```

imprime le HTML de la page sur la sortie standard, tel que ce programme le
construit : les filtres tournent, la page 404 répond à un chemin sans route,
les en-têtes de `secure` y sont. C'est ce qu'un éditeur ou une étape de
construction devrait demander plutôt que deviner.

Le serveur lancé, depuis un autre terminal :

```sh
curl -i http://127.0.0.1:8080/
```

```
HTTP/1.1 200 OK
content-type: text/html; charset=utf-8
vary: accept-encoding
content-length: 320
connection: keep-alive
```

## 5. L'arrêter, et le mettre en service

Ctrl-C, et ce qu'un gestionnaire de services envoie, ne tuent pas le
processus : ils lui demandent de s'arrêter, l'écoute se ferme, et les
connexions au milieu d'une réponse ont cinq secondes pour finir. Lancer une
seconde copie sur le même port le dit et sort :

```
runtime error: kealeb could not start: port 8080 is already taken
```

`run(8080)` écoute sur `127.0.0.1` et ne peut surprendre personne. Pour une
machine que d'autres atteignent :

```keal
site.run(8080, "")                    // toutes les interfaces
site.log = false                      // pas une ligne par requête
```

Il n'y a pas de TLS. Mettez-le derrière un mandataire inverse, qui est là où
un terminateur a sa place ; la sortie standard est vidée ligne par ligne dès
que le serveur démarre, donc un journal envoyé dans un fichier ou lu par un
superviseur arrive à mesure qu'il s'écrit. Le [§13 du
guide](guide.fr.md#13-la-mise-en-service) donne les limites réglables —
tailles d'en-tête et de corps, temps d'inactivité, requêtes par connexion — et
[l'ordre de l'arrêt](guide.fr.md#l-arr-t).

## 6. Ce que vous pouvez y mettre

Tout ce qui suit est un appel sur `site`, ou un import de plus. Chaque ligne
renvoie à la section du guide qui l'explique.

| Je veux | écrire | guide |
|---|---|---|
| une page | `site.page("/apropos", { req -> column([h1("À propos")]) })` | [§6](guide.fr.md#6-les-pages) |
| une route qui répond du texte | `site.get("/ping", { req -> text("pong") })` | [§3](guide.fr.md#3-les-routes) |
| un chemin avec un paramètre | `site.get("/user/{id}", { req -> text(req.param("id")) })` | [§3](guide.fr.md#ce-qu-un-motif-peut-dire) |
| du JSON en entrée et en sortie | `parseJson(req.text())`, `jsonBody(jObj(fields).write())` | [§10](guide.fr.md#10-json) |
| un formulaire, sans JavaScript | `site.formPage("/inscription", build, onPost)` | [§7](guide.fr.md#7-les-formulaires-sans-javascript) |
| un envoi de fichier | `req.file("doc")`, puis `.saveTo(chemin)` | [§7](guide.fr.md#les-fichiers) |
| une page vivante — l'état sur le serveur, seule la différence traverse | `site.livePage("/", { req -> view({ -> … }) })` | [§8](guide.fr.md#8-les-pages-vivantes) |
| une feuille de style écrite en Keal | `site.css(sheet([rule(".hero").bg("…")]))` | [§6](guide.fr.md#des-styles-crits-en-keal) |
| mon propre JavaScript | `site.script("…")` | [§6](guide.fr.md#le-javascript-et-quand-il-en-faut) |
| un répertoire de fichiers statiques | `site.files("/static", "./public")` | [§9](guide.fr.md#9-les-fichiers-statiques) |
| mes propres pages 404 et d'erreur | `site.onNotFound(build)`, `site.onError(build)` | [§13](guide.fr.md#quand-il-n-y-a-rien-et-quand-quelque-chose-a-cass) |
| quelque chose autour de chaque requête — journal, mur de connexion | `site.use({ req, next -> next.on(req) })` | [§12](guide.fr.md#12-les-filtres) |
| du travail à intervalle | `site.every(60000, job)`, `site.after(5000, job)` | [§14](guide.fr.md#14-le-travail-programm) |
| une base de données | `import "dep:kealeb/src/sql.keal"`, construire avec `-lsqlite3` | [§15](guide.fr.md#15-une-base-de-donn-es) |
| connexion, sessions, CSRF, les en-têtes de sécurité | `import "dep:kealeb/src/auth.keal"`, puis `site.secure(auth(secret))` | [§16](guide.fr.md#16-la-s-curit) |
| des tests sans socket | `dispatch(router, request("GET", "/x"))` | [§11](guide.fr.md#11-les-tests) |
| savoir ce que le cadriciel ne fera pas | | [§17](guide.fr.md#17-ce-que-le-cadriciel-ne-fera-pas) |

Les chemins des lignes d'import sont ceux qu'un projet hors de ce dépôt écrit.
À l'intérieur, les exemples disent `../kealeb.keal` et `../src/sql.keal`.

## 7. Quand ça ne marche pas

**`no keal compiler found — set KEAL, or build ../keal`.** Le script a
cherché dans `$KEAL`, à côté du projet, et sur le chemin. Finissez le §2, ou
dites-lui où est le compilateur : `KEAL=/chemin/vers/keal tools/build.sh
app.keal`.

**`` `func main` must declare what it returns``.** Un point d'entrée qui ne
répond rien est un `proc main()`. Et ne l'appelez pas : Keal lance `main` tout
seul une fois le premier niveau exécuté, donc une ligne `main()` en bas fait
tourner tout le programme deux fois.

**`the C backend cannot compile nested functions yet`.** Une fonction
auxiliaire dans un gestionnaire veut être une fonction de premier niveau.
`examples/todo.keal` montre la forme.

**`référence indéfinie vers « sqlite3_close »`**, et une douzaine de lignes de
l'éditeur de liens comme elle. Le programme importe `src/sql.keal` et la
construction n'a pas dit `-lsqlite3`. Ajoutez-le après le fichier source.

**`port 8080 is already taken`.** Une autre copie tourne, ou autre chose.
Arrêtez-la, ou choisissez un autre numéro dans `run`.

**La page est là, mais une page vivante ne réagit pas au clic.** Regardez la
console du navigateur : le client ouvre une WebSocket vers `/kealeb/live`, et
un mandataire inverse devant le serveur doit laisser passer les mises à
niveau.
